#!/usr/bin/env python3
"""Verify guarded commits on disposable repositories."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, 'hooks'))
import commit_par_zone as CPZ
import git_guard
fails = []

def ok(m):
    print('  ✅ %s' % m)

def ko(m):
    print('  ❌ %s' % m)
    fails.append(m)

def depot(hook=None):
    d = tempfile.mkdtemp(prefix='cpz-governed-')
    if not os.path.realpath(d).startswith(os.path.realpath(tempfile.gettempdir()) + os.sep):
        raise RuntimeError('isolation')
    os.makedirs(os.path.join(d, 'state'))
    for z in ('lessons', 'hooks', 'sessions'):
        os.makedirs(os.path.join(d, z), exist_ok=True)
    subprocess.run(['git', 'init', '-q', '--initial-branch=main', '.'], cwd=d)
    for c, v in (('user.name', 'S'), ('user.email', 's@l'), ('commit.gpgsign', 'false')):
        subprocess.run(['git', 'config', c, v], cwd=d)
    open(os.path.join(d, '.gitignore'), 'w').write('state/\n')
    open(os.path.join(d, 'lessons', 'base.md'), 'w').write('base\n')
    subprocess.run(['git', 'add', '-A'], cwd=d)
    subprocess.run(['git', 'commit', '-q', '-m', 'C0'], cwd=d)
    if hook:
        h = os.path.join(d, '.git', 'hooks', 'pre-commit')
        open(h, 'w').write('#!/bin/sh\n' + hook + '\nexit 0\n')
        os.chmod(h, 493)
    return d

def fichiers_du_commit(d, ref='HEAD'):
    r = subprocess.run(['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', ref], cwd=d, capture_output=True, text=True)
    return sorted((x for x in r.stdout.splitlines() if x))

def index(d):
    r = subprocess.run(['git', 'diff', '--cached', '--name-only'], cwd=d, capture_output=True, text=True)
    return sorted((x for x in r.stdout.splitlines() if x))

def head(d):
    return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=d, capture_output=True, text=True).stdout.strip()

def journal(d):
    try:
        return [json.loads(l) for l in open(os.path.join(d, 'state', 'git-journal.jsonl'), encoding='utf-8')]
    except Exception:
        return []

def case_1():
    print('1. Normal single-zone commit')
    d = depot()
    try:
        open(os.path.join(d, 'lessons', 'new.md'), 'w').write('x\n')
        n = CPZ.commit_by_zone(d, 'test: ')
        f = fichiers_du_commit(d)
        ok('exactly one planned commit') if n == 1 and f == ['lessons/new.md'] else ko('expected one new lesson in commit')
        ok('untracked file was added') if f == ['lessons/new.md'] else ko('untracked file was omitted')
        ok('lock released') if git_guard.diagnostic(d)['state'] == 'free' else ko('lock held after commit')
    finally:
        shutil.rmtree(d, ignore_errors=True)

def case_2():
    print('2a. External index writer during commit')
    injection = 'cd "$(git rev-parse --show-toplevel)" && unset GIT_INDEX_FILE && echo outsider > lessons/outsider.md && git add -- lessons/outsider.md'
    d = depot(hook=injection)
    try:
        open(os.path.join(d, 'lessons', 'mine.md'), 'w').write('x\n')
        CPZ.commit_by_zone(d, 'test: ')
        f = fichiers_du_commit(d)
        if f == ['lessons/mine.md']:
            ok('commit stays within pathspec')
        else:
            ko('commit contains outsider file')
        if os.path.exists(os.path.join(d, 'lessons', 'outsider.md')):
            ok('outsider actually wrote a file')
        else:
            ko('injection did not run')
        chemin = os.path.join(d, 'lessons', 'outsider.md')
        if os.path.exists(chemin) and open(chemin).read().strip() == 'outsider':
            ok('outsider file content survives')
        else:
            ko('outsider file content lost')
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print('2c. Previously staged third-party file')
    d = depot()
    try:
        open(os.path.join(d, 'lessons', 'third-party.md'), 'w').write('work by another agent\n')
        subprocess.run(['git', 'add', '--', 'lessons/third-party.md'], cwd=d)
        open(os.path.join(d, 'hooks', 'mine.py'), 'w').write('x\n')
        CPZ.commit_by_zone(d, 'test: ')
        knowledge, engine = (fichiers_du_commit(d, 'HEAD~1'), fichiers_du_commit(d, 'HEAD'))
        if knowledge == ['lessons/third-party.md'] and engine == ['hooks/mine.py']:
            ok('each file committed in its own zone')
        else:
            ko('files crossed zone boundaries')
        perdus = [f for f in ('lessons/third-party.md', 'hooks/mine.py') if f not in knowledge + engine]
        ok('no third-party work lost') if not perdus else ko('no third-party work lost')
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print('2b. Hook index writes are a known limit')
    injection2 = 'cd "$(git rev-parse --show-toplevel)" && echo internal > lessons/internal.md && git add -- lessons/internal.md'
    d = depot(hook=injection2)
    try:
        open(os.path.join(d, 'lessons', 'mine.md'), 'w').write('x\n')
        CPZ.commit_by_zone(d, 'test: ')
        f = fichiers_du_commit(d)
        if 'lessons/internal.md' in f:
            ok('hook write reaches temporary index')
            ok('pathspec limit is reproducible')
        else:
            ko('pathspec limit changed')
    finally:
        shutil.rmtree(d, ignore_errors=True)

def case_3_4():
    for nom, op, geste in (('3. CONCURRENT RESET', 'reset', 'git reset -q'), ('4. CONCURRENT COMMIT', 'commit', 'git commit -q --allow-empty -m intruder')):
        print('3-4. Competing lock acquisition')
        injection = 'cd "$(git rev-parse --show-toplevel)" && %s -c "import sys;sys.path.insert(0,\'%s\');import git_guard,os,json;j=git_guard.acquerir(\'intruder\',\'%s\',None,depot=os.getcwd());open(\'state/INTRUDER\',\'w\').write(\'ACQUIRED\' if j else \'REFUSED\');(%s) if j else None"' % (sys.executable, os.path.join(BRAIN, 'hooks'), op, 'None')
        d = depot(hook=injection)
        try:
            open(os.path.join(d, 'lessons', 'mine.md'), 'w').write('x\n')
            avant = head(d)
            n = CPZ.commit_by_zone(d, 'test: ')
            verdict = open(os.path.join(d, 'state', 'INTRUDER')).read() if os.path.exists(os.path.join(d, 'state', 'INTRUDER')) else 'ABSENT'
            ok('intruder refused the lock') if verdict == 'REFUSED' else ko('intruder acquired the lock')
            f = fichiers_du_commit(d)
            if n == 1 and f == ['lessons/mine.md'] and (head(d) != avant):
                ok('planned commit completed')
            else:
                ko('planned commit failed')
        finally:
            shutil.rmtree(d, ignore_errors=True)

def case_5():
    print('5. Two sequential zone commits')
    d = depot()
    try:
        open(os.path.join(d, 'lessons', 'knowledge.md'), 'w').write('x\n')
        open(os.path.join(d, 'hooks', 'engine.py'), 'w').write('y\n')
        n = CPZ.commit_by_zone(d, 'test: ')
        c1 = fichiers_du_commit(d, 'HEAD')
        c2 = fichiers_du_commit(d, 'HEAD~1')
        if n == 2 and {tuple(c1), tuple(c2)} == {('hooks/engine.py',), ('lessons/knowledge.md',)}:
            ok('commits split by zone')
        else:
            ko('commits not split by zone')
        pris = [e for e in journal(d) if e['event'] == 'acquired']
        if len(pris) == 2 and {e.get('zone') for e in pris} == {'knowledge', 'engine'}:
            ok('two journal acquisitions have correct zones')
        else:
            ko('journal zones incorrect')
    finally:
        shutil.rmtree(d, ignore_errors=True)

def case_6():
    print('6. Missing guard refuses commit')
    d = depot()
    isolated = tempfile.mkdtemp(prefix='without-guard-')
    try:
        shutil.copy(os.path.join(BRAIN, 'hooks', 'commit_par_zone.py'), isolated)
        open(os.path.join(d, 'lessons', 'new.md'), 'w').write('x\n')
        avant = head(d)
        r = subprocess.run([sys.executable, os.path.join(isolated, 'commit_par_zone.py')], cwd=d, capture_output=True, text=True, env=dict(os.environ, BRAIN_HOME=d, PYTHONPATH=isolated))
        sortie = r.stdout + r.stderr
        if 'git_guard unavailable' in sortie:
            ok('guard absence reported')
        else:
            ko('guard absence not reported')
        if head(d) == avant:
            ok('HEAD unchanged without guard')
        else:
            ko('commit made without guard')
        if index(d) == []:
            ok('index unchanged without guard')
        else:
            ko('index changed without guard')
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(isolated, ignore_errors=True)

def case_7():
    print('7. Journal attributes and certifies commit')
    d = depot()
    try:
        open(os.path.join(d, 'lessons', 'new.md'), 'w').write('x\n')
        CPZ.commit_by_zone(d, 'test: ')
        j = journal(d)
        a = next((e for e in j if e['event'] == 'acquired'), {})
        l = next((e for e in j if e['event'] == 'released'), {})
        manque = [c for c in ('actor', 'pid', 'operation', 'scope', 'head_before', 'zone', 'origin') if c not in a]
        if manque:
            ko('acquisition fields missing')
        else:
            ok('acquisition fields complete')
        if l.get('committed_files') == ['lessons/new.md'] and l.get('head_moved'):
            ok('release certifies committed files and HEAD change')
        else:
            ko('release certification incorrect')
        if l.get('out_of_scope') == []:
            ok('no files outside requested scope')
        else:
            ko('out-of-scope files committed')
    finally:
        shutil.rmtree(d, ignore_errors=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sabotage-zone', action='store_true',
                        help='Force all changed files into one commit zone')
    args = parser.parse_args()
    if args.sabotage_zone:
        CPZ.zone = lambda path: 'knowledge'
    print('==============================================================================')
    print('Guarded zone commits on disposable repositories')
    print('==============================================================================')
    for f in (case_1, case_2, case_3_4, case_5, case_6, case_7):
        try:
            f()
        except Exception as error:
            ko(f'{f.__name__} raised: {error}')
    print('------------------------------------------------------------------------------')
    if fails:
        print('FAIL: guarded zone commit checks')
        for f in fails:
            print('See failed assertion above')
        return 1
    print('PASS: guarded zone commit checks')
    print('Scope: disposable repositories on one host.')
    print('Other commit producers are outside this bench.')
    return 0
if __name__ == '__main__':
    sys.exit(main())
