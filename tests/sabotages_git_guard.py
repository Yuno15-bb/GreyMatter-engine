#!/usr/bin/env python3
"""Exercise Git lock invariants on disposable repositories."""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, 'hooks'))
import git_guard
fails = []

def ok(m):
    print('  ✅ %s' % m)

def ko(m):
    print('  ❌ %s' % m)
    fails.append(m)

def depot():
    d = tempfile.mkdtemp(prefix='bench-git-guard-')
    if not os.path.realpath(d).startswith(os.path.realpath(tempfile.gettempdir()) + os.sep):
        raise RuntimeError('isolation')
    os.makedirs(os.path.join(d, 'state'))
    subprocess.run(['git', 'init', '-q', '--initial-branch=main', '.'], cwd=d)
    for c, v in (('user.name', 'S'), ('user.email', 's@l'), ('commit.gpgsign', 'false')):
        subprocess.run(['git', 'config', c, v], cwd=d)
    open(os.path.join(d, 'f.md'), 'w').write('base\n')
    subprocess.run(['git', 'add', 'f.md'], cwd=d)
    subprocess.run(['git', 'commit', '-q', '-m', 'C0'], cwd=d)
    return d

def journal(d):
    try:
        return [json.loads(l) for l in open(os.path.join(d, 'state', 'git-journal.jsonl'), encoding='utf-8')]
    except Exception:
        return []

def lock_path(d):
    return os.path.join(d, 'state', 'git.lock')

def case_5():
    print('case_5: scenario 75')
    d = depot()
    try:
        top = os.path.join(d, 'TOP')
        code = "import sys,os,time;sys.path.insert(0,%r);import git_guard\nopen(%r+'/READY-%%s','w').write('1')\nwhile not os.path.exists(%r): time.sleep(0.005)\nj=git_guard.acquerir('actor-%%s','commit',['f.md'],depot=%r)\nprint('ACQUIRED' if j else 'REFUSED',flush=True)\nif j:\n    time.sleep(1.5)\n    git_guard.liberer(j,%r)\n" % (os.path.join(BRAIN, 'hooks'), d, top, d, d)
        procs = [subprocess.Popen([sys.executable, '-c', code % (i, i)], stdout=subprocess.PIPE, text=True) for i in range(8)]
        limite = time.time() + 30
        while len([f for f in os.listdir(d) if f.startswith('READY-')]) < 8:
            if time.time() > limite:
                ko('case_5: check 98')
                return
            time.sleep(0.01)
        open(top, 'w').write('go')
        sorties = [p.communicate()[0].strip() for p in procs]
        gagnants = sorties.count('ACQUIRED')
        if gagnants == 1:
            ok('case_5: check 106')
        else:
            ko('case_5: check 108')
        refus = [e for e in journal(d) if e['event'] == 'refused']
        if refus and all((e.get('current_owner') for e in refus)):
            ok('case_5: check 111')
        else:
            ko('case_5: check 114')
        if not [e for e in journal(d) if e['event'] == 'zombie_recovery']:
            ok('case_5: check 116')
        else:
            ko('case_5: check 118')
    finally:
        shutil.rmtree(d, ignore_errors=True)

def case_6():
    print('case_6: scenario 125')
    d = depot()
    try:
        mort = subprocess.Popen([sys.executable, '-c', 'pass'])
        mort.wait()
        json.dump({'actor': 'ghost', 'pid': mort.pid, 'started': 'long-ago', 'operation': 'commit', 'scope': ['f.md'], 'ts': time.time(), 'head_before': 'x'}, open(lock_path(d), 'w'))
        diag = git_guard.diagnostic(d)
        if diag['state'] == 'recoverable':
            ok('case_6: check 135')
        else:
            ko('case_6: check 137')
        j = git_guard.acquerir('repreneur', 'commit', ['f.md'], depot=d)
        if j:
            ok('case_6: check 141')
        else:
            ko('case_6: check 143')
        ev = [e['event'] for e in journal(d)]
        if 'zombie_recovery' in ev:
            ok('case_6: check 146')
        else:
            ko('case_6: check 149')
        git_guard.liberer(j, d)
    finally:
        shutil.rmtree(d, ignore_errors=True)

def case_7():
    print('case_7: scenario 157')
    d = depot()
    dormeur = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(60)'])
    try:
        time.sleep(0.3)
        json.dump({'actor': 'slow-push', 'pid': dormeur.pid, 'started': git_guard._demarrage(dormeur.pid), 'operation': 'push', 'scope': None, 'ts': time.time() - 10 * git_guard.TTL, 'head_before': 'x'}, open(lock_path(d), 'w'))
        diag = git_guard.diagnostic(d)
        if diag['state'] == 'held' and diag.get('ttl_exceeded'):
            ok('case_7: check 169')
        else:
            ko('case_7: check 172')
        j = git_guard.acquerir('thief', 'commit', ['f.md'], depot=d)
        if j is None:
            ok('case_7: check 176')
        else:
            ko('case_7: check 178')
        if os.path.exists(lock_path(d)) and json.load(open(lock_path(d)))['actor'] == 'slow-push':
            ok('case_7: check 181')
        else:
            ko('case_7: check 183')
    finally:
        dormeur.kill()
        dormeur.wait()
        shutil.rmtree(d, ignore_errors=True)

def case_8():
    print('case_8: scenario 191')
    d = depot()
    try:
        code = "import sys,time;sys.path.insert(0,%r);import git_guard;git_guard.acquerir('killed-mid-flight','commit',['f.md'],depot=%r);print('HELD',flush=True);time.sleep(60)" % (os.path.join(BRAIN, 'hooks'), d)
        p = subprocess.Popen([sys.executable, '-c', code], stdout=subprocess.PIPE, text=True)
        p.stdout.readline()
        os.kill(p.pid, signal.SIGKILL)
        p.wait()
        if os.path.exists(lock_path(d)):
            json.load(open(lock_path(d)))
            ok('case_8: check 204')
        else:
            ko('case_8: check 207')
        states = {git_guard.diagnostic(d)['state'] for _ in range(5)}
        if states == {'recoverable'}:
            ok('case_8: check 210')
        else:
            ko('case_8: check 212')
        j = git_guard.acquerir('suivant', 'commit', ['f.md'], depot=d)
        ok('case_8: check 214') if j else ko('case_8: check 214')
        n = subprocess.run(['git', 'rev-list', '--count', 'HEAD'], cwd=d, capture_output=True, text=True).stdout.strip()
        ok('case_8: check 218') if n == '1' else ko('case_8: check 219')
        git_guard.liberer(j, d)
    finally:
        shutil.rmtree(d, ignore_errors=True)

def case_9():
    print('case_9: scenario 227')
    d = depot()
    try:
        for mauvais in (None, '', '   ', 42):
            if git_guard.acquerir(mauvais, 'commit', ['f.md'], depot=d) is not None:
                ko('case_9: check 232')
                break
        else:
            ok('case_9: check 235')
        refus = [e for e in journal(d) if e['event'] == 'refused_missing_identity']
        ok('case_9: check 237') if len(refus) == 4 else ko('case_9: check 238')
        if not os.path.exists(lock_path(d)):
            ok('case_9: check 240')
        else:
            ko('case_9: check 242')
    finally:
        shutil.rmtree(d, ignore_errors=True)

def case_10():
    print('case_10: scenario 249')
    d = depot()
    dormeur = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(60)'])
    try:
        time.sleep(0.3)
        json.dump({'actor': 'old-owner', 'pid': dormeur.pid, 'started': 'Mon Jan  1 00:00:00 1990', 'operation': 'commit', 'scope': None, 'ts': time.time(), 'head_before': 'x'}, open(lock_path(d), 'w'))
        diag = git_guard.diagnostic(d)
        if diag['state'] == 'recoverable' and 'reused' in (diag.get('reason') or ''):
            ok('case_10: check 262')
        else:
            ko(f'PID reuse was not detected: {diag}')
    finally:
        dormeur.kill()
        dormeur.wait()
        shutil.rmtree(d, ignore_errors=True)

def case_11():
    print('case_11: scenario 273')
    d = depot()
    try:
        real = git_guard.acquerir('owner', 'commit', ['f.md'], depot=d)
        fake = dict(real, actor='impostor', pid=real['pid'] + 1, ts=real['ts'] + 1)
        git_guard.liberer(fake, d)
        if os.path.exists(lock_path(d)):
            ok('case_11: check 280')
        else:
            ko('case_11: check 282')
        git_guard.liberer(real, d)
        ok('case_11: check 284') if not os.path.exists(lock_path(d)) else ko('case_11: check 285')
    finally:
        shutil.rmtree(d, ignore_errors=True)

def case_12():
    print('case_12: scenario 292')
    d = depot()
    try:
        with git_guard.transaction('actor-A', 'commit', ['f.md'], depot=d):
            subprocess.run(['git', 'commit', '-q', '--allow-empty', '-m', 'x'], cwd=d)
            refused = git_guard.acquerir('actor-B', 'reset', ['f.md'], depot=d)
        j = journal(d)
        manque = []
        acquired = next((e for e in j if e['event'] == 'acquired'), {})
        for champ in ('actor', 'pid', 'operation', 'scope', 'head_before', 'when'):
            if not acquired.get(champ) and acquired.get(champ) != []:
                manque.append('acquired.' + champ)
        ref = next((e for e in j if e['event'] == 'refused'), {})
        if not ref.get('current_owner'):
            manque.append('refused.current_owner')
        lib = next((e for e in j if e['event'] == 'released'), {})
        for champ in ('head_after', 'committed_files', 'duration_s'):
            if champ not in lib:
                manque.append('released.' + champ)
        if manque:
            ko('case_12: check 312')
        else:
            ok('case_12: check 314')
        if refused is None and ref.get('actor') == 'actor-B' and (ref['current_owner'].get('actor') == 'actor-A'):
            ok('case_12: check 318')
        else:
            ko('case_12: check 320')
        if lib.get('head_moved') is True and lib.get('head_after') != lib.get('head_before'):
            ok('case_12: check 323')
        else:
            ko('case_12: check 326')
    finally:
        shutil.rmtree(d, ignore_errors=True)

def main():
    print('main: scenario 332')
    print('main: scenario 333')
    print('main: scenario 334')
    print('main: scenario 335')
    for f in (case_5, case_6, case_7, case_8, case_9, case_10, case_11, case_12):
        try:
            f()
        except Exception as error:
            ko(f'{f.__name__} raised: {error}')
    print('main: scenario 342')
    if fails:
        print('main: scenario 344')
        for f in fails:
            print('main: scenario 346')
        return 1
    print('main: scenario 348')
    print('main: scenario 349')
    print('main: scenario 350')
    return 0
if __name__ == '__main__':
    sys.exit(main())
