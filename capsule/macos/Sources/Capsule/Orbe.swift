// THE ORB in Metal: a faithful port of the WebGL orb (`orbe/orbe.js` + `orbe/snoise.glsl`).
// Same sphere (icosahedron subdivided 88 times), same ten mechanics, same glass, same camera
// (42°, z = 4.6), same rotation, same 1.4 s fade, same frame rates.
//
// What changes with Metal, and why:
//   · GLSL's `mod` rounds down, Metal's `fmod` rounds towards zero: the noise takes negative
//     indices, so `gmod` redoes GLSL's;
//   · `smoothstep` with inverted bounds (0.10 → -0.75) is defined by neither standard:
//     `lisse` writes the formula the drivers apply;
//   · Three.js indexes vertices flat (one triangle = three new vertices); here they are shared
//     within each face. Same shape on screen, three times fewer vertices computed.
import AppKit
import Metal
import QuartzCore
import simd

private let SHADER = """
#include <metal_stdlib>
using namespace metal;

struct U {
  float4x4 mv, proj; float3x3 nrm;
  float uPhase, uDisp, uFreq, uSpeed, uModeA, uModeB, uMix, uRimI, uSweep, uVerre;
  float3 uC1, uC2, uC3, uRim;
};
struct VO { float4 pos [[position]]; float3 vNormal; float3 vView; float vDisp; };

float4 gmod(float4 x, float y) { return x - y * floor(x / y); }
float3 gmod(float3 x, float y) { return x - y * floor(x / y); }
float lisse(float a, float b, float x) { float t = clamp((x - a) / (b - a), 0.0, 1.0); return t * t * (3.0 - 2.0 * t); }

float4 permute(float4 x){ return gmod(((x*34.0)+1.0)*x, 289.0); }
float4 taylorInvSqrt(float4 r){ return 1.79284291400159-0.85373472095314*r; }
float snoise(float3 v){
  const float2 C=float2(1.0/6.0,1.0/3.0); const float4 D=float4(0.0,0.5,1.0,2.0);
  float3 i=floor(v+dot(v,C.yyy)); float3 x0=v-i+dot(i,C.xxx);
  float3 g=step(x0.yzx,x0.xyz); float3 l=1.0-g; float3 i1=min(g.xyz,l.zxy); float3 i2=max(g.xyz,l.zxy);
  float3 x1=x0-i1+1.0*C.xxx; float3 x2=x0-i2+2.0*C.xxx; float3 x3=x0-1.0+3.0*C.xxx;
  i=gmod(i,289.0);
  float4 p=permute(permute(permute(i.z+float4(0.0,i1.z,i2.z,1.0))+i.y+float4(0.0,i1.y,i2.y,1.0))+i.x+float4(0.0,i1.x,i2.x,1.0));
  float n_=1.0/7.0; float3 ns=n_*D.wyz-D.xzx;
  float4 j=p-49.0*floor(p*ns.z*ns.z);
  float4 x_=floor(j*ns.z); float4 y_=floor(j-7.0*x_);
  float4 x=x_*ns.x+ns.yyyy; float4 y=y_*ns.x+ns.yyyy; float4 h=1.0-abs(x)-abs(y);
  float4 b0=float4(x.xy,y.xy); float4 b1=float4(x.zw,y.zw);
  float4 s0=floor(b0)*2.0+1.0; float4 s1=floor(b1)*2.0+1.0; float4 sh=-step(h,float4(0.0));
  float4 a0=b0.xzyw+s0.xzyw*sh.xxyy; float4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  float3 p0=float3(a0.xy,h.x); float3 p1=float3(a0.zw,h.y); float3 p2=float3(a1.xy,h.z); float3 p3=float3(a1.zw,h.w);
  float4 norm=taylorInvSqrt(float4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  float4 m=max(0.6-float4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
  return 42.0*dot(m*m,float4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}

float champUn(float3 p, float uMode, constant U& u){
  float t = u.uPhase; float F = u.uFreq;
  float3 flux = float3(0.0, -t*0.55, 0.0);
  if(uMode<0.5){ return snoise(p*F*0.55 + flux)*0.9; }                        // 0 swell
  if(uMode<1.5){ float onde = sin(p.y*F*5.0 + t*3.2);                          // 1 sweep
                 return onde*0.72 + snoise(p*F*1.1 + flux)*0.28; }
  if(uMode<2.5){ float n = snoise(p*F*0.9 + flux); return mix(floor(n*4.0)/4.0, n, 0.25); }  // 2 plates
  if(uMode<3.5){ return abs(snoise(p*F + flux))*0.55                           // 3 boiling
                      + abs(snoise(p*F*2.7 + flux*1.3))*0.30
                      + abs(snoise(p*F*5.3 + flux*2.1))*0.15 - 0.45; }
  if(uMode<4.5){ float d = acos(clamp(p.y,-1.0,1.0))/3.14159;                  // 4 shock wave
                 float front = fract(t*0.30); float e = (d-front)*18.0;
                 return exp(-(e*e))*1.2 - 0.15; }
  if(uMode<5.5){ float mind = 1e9;                                             // 5 cells
                 for(int i=0;i<6;i++){ float fi = float(i);
                   float3 g = normalize(float3(sin(fi*2.1+t*0.7), cos(fi*1.7+t*0.5), sin(fi*3.3+t*0.6)));
                   mind = min(mind, distance(p, g)); }
                 return (0.9 - mind*0.9)*1.4; }
  if(uMode<6.5){ float a = p.y*1.9 + t*0.55; float c = cos(a), s = sin(a);     // 6 vortex
                 float3 q = float3(p.x*c - p.z*s, p.y, p.x*s + p.z*c);
                 return snoise(q*F*0.95 + flux*0.7)*0.95; }
  if(uMode<7.5){ return sin(t*1.6)*0.55 + sin(p.y*1.8 + t*0.9)*0.35; }       // 7 breathing
  if(uMode<8.5){ float a = sin(p.x*F*4.5 + t*2.0); float b = sin(p.z*F*4.5 + t*1.6);  // 8 interference
                 float c = sin(p.y*F*3.0 + t*2.4); return (a*b + c*0.5)*0.7; }
  float n = snoise(p*F*0.95 + flux*1.8);                                       // 9 shards
  float pic = pow(max(n,0.0), 3.0);
  float fond = snoise(p*F*0.5 + flux)*0.30;
  return pic*1.5 + fond - 0.16;
}
float champ(float3 p, constant U& u){
  float f = champUn(p, u.uModeA, u);
  if(u.uMix > 0.001) f = mix(f, champUn(p, u.uModeB, u), u.uMix);
  return f;
}
float3 deplace(float3 sp, constant U& u){ return sp + sp*champ(sp, u)*u.uDisp; }

vertex VO vs(uint vid [[vertex_id]], const device packed_float3* P [[buffer(0)]], constant U& u [[buffer(1)]]) {
  float3 sp=normalize(float3(P[vid]));
  float3 T=normalize(cross(sp, abs(sp.y)<0.99?float3(0.0,1.0,0.0):float3(1.0,0.0,0.0)));
  float3 Bn=cross(sp,T); float e=0.012;
  float3 p0=deplace(sp,u), p1=deplace(normalize(sp+T*e),u), p2=deplace(normalize(sp+Bn*e),u);
  float3 n=normalize(cross(p1-p0,p2-p0)); if(dot(n,sp)<0.0) n=-n;
  VO o;
  o.vDisp = champ(sp, u);
  float4 mv = u.mv*float4(p0,1.0);
  o.vNormal = normalize(u.nrm*n); o.vView = normalize(-mv.xyz);
  o.pos = u.proj*mv;
  return o;
}

fragment float4 fs(VO in [[stage_in]], constant U& u [[buffer(1)]]) {
  float3 N=normalize(in.vNormal), V=normalize(in.vView); float vDisp = in.vDisp;
  float d=clamp(dot(N,V),0.0,1.0);
  float f=pow(1.0-d,2.4)*u.uRimI;
  float3 base=mix(u.uC3,u.uC2,lisse(-0.6,0.9,vDisp));
  base=mix(base,u.uC1,pow(d,3.0)*0.75);
  float3 L=normalize(float3(0.6,0.8,0.7));
  float spec=pow(max(dot(reflect(-L,N),V),0.0),34.0)*u.uSweep;
  float3 plein=base + u.uRim*f*0.85 + float3(spec)*0.55;

  const float BRILLANCE = 0.26; const float REFLET = 0.34; const float COEUR = 0.78; const float BORD = 0.30;
  float ep=pow(1.0-d,1.55);
  ep=clamp(ep+lisse(0.10,-0.75,vDisp)*0.16,0.0,1.0);
  ep=clamp(ep*(0.90+0.26*lisse(-0.9,0.9,vDisp)),0.0,1.0);
  float3 teinte=mix(u.uC3*0.60,u.uC2*1.30,clamp(ep*1.30,0.0,1.0));
  float3 R=reflect(-V,N);
  float ciel=lisse(-0.10,0.30,R.y);
  float3 env=mix(float3(0.05,0.06,0.09),float3(0.52,0.57,0.66),ciel);
  float fres=(0.04+0.62*pow(1.0-d,4.0))*REFLET;
  float3 H=normalize(L+V);
  float dur  =pow(max(dot(N,H),0.0), 80.0)*u.uSweep*BRILLANCE;
  float large=pow(max(dot(N,H),0.0), 10.0)*u.uSweep*BRILLANCE;
  float tranche=lisse(0.90,0.999,1.0-d);
  float3 verre=teinte + env*fres + u.uRim*f*0.42
             + (u.uRim*0.55+float3(0.10))*tranche*0.45
             + float3(large)*0.10 + float3(dur)*0.45;
  float a=clamp(COEUR + BORD*ep + dur*0.45 + large*0.06 + tranche*0.22,0.0,1.0);
  return float4(mix(plein,verre,u.uVerre), mix(1.0,a,u.uVerre));
}
"""

/// Same layout as the shader's `struct U` (float4x4, float3x3 = 3 columns of 16 bytes,
/// then ten floats, then four float3 aligned on 16).
private struct Uniformes {
    var mv = matrix_identity_float4x4, proj = matrix_identity_float4x4, nrm = matrix_identity_float3x3
    var uPhase: Float = 0, uDisp: Float = 0, uFreq: Float = 0, uSpeed: Float = 0
    var uModeA: Float = 0, uModeB: Float = 0, uMix: Float = 0, uRimI: Float = 0, uSweep: Float = 1, uVerre: Float = 1
    var uC1 = SIMD3<Float>(), uC2 = SIMD3<Float>(), uC3 = SIMD3<Float>(), uRim = SIMD3<Float>()
}

/// Three.js r160 IcosahedronGeometry(1, detail): the same split of each face.
private func icosphere(_ detail: Int) -> ([Float], [UInt32]) {
    let t = Float((1 + 5.0.squareRoot()) / 2)
    let v: [SIMD3<Float>] = [[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t],
                             [0, -1, -t], [0, 1, -t], [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]]
    let f = [0, 11, 5, 0, 5, 1, 0, 1, 7, 0, 7, 10, 0, 10, 11, 1, 5, 9, 5, 11, 4, 11, 10, 2, 10, 7, 6, 7, 1, 8,
             3, 9, 4, 3, 4, 2, 3, 2, 6, 3, 6, 8, 3, 8, 9, 4, 9, 5, 2, 4, 11, 6, 2, 10, 8, 6, 7, 9, 8, 1]
    let cols = detail + 1
    var pos: [Float] = [], idx: [UInt32] = []
    for k in stride(from: 0, to: f.count, by: 3) {
        let a = v[f[k]], b = v[f[k + 1]], c = v[f[k + 2]]
        // Three's grid: row i between (a→c) and (b→c), cols - i + 1 points
        var ligne: [[UInt32]] = []
        for i in 0...cols {
            let aj = a + (c - a) * Float(i) / Float(cols), bj = b + (c - b) * Float(i) / Float(cols)
            let rows = cols - i
            var l: [UInt32] = []
            for j in 0...rows {
                let p = (j == 0 && i == cols) ? aj : aj + (bj - aj) * Float(j) / Float(rows)
                let n = simd_normalize(p)
                l.append(UInt32(pos.count / 3)); pos += [n.x, n.y, n.z]
            }
            ligne.append(l)
        }
        for i in 0..<cols {
            for j in 0..<(2 * (cols - i) - 1) {
                let kk = j / 2
                if j % 2 == 0 { idx += [ligne[i][kk + 1], ligne[i + 1][kk], ligne[i][kk]] }
                else { idx += [ligne[i][kk + 1], ligne[i + 1][kk + 1], ligne[i + 1][kk]] }
            }
        }
    }
    return (pos, idx)
}

private func perspective(fovDeg: Float, near: Float, far: Float) -> float4x4 {
    let f = 1 / tan(fovDeg * .pi / 360)
    return float4x4(columns: (SIMD4(f, 0, 0, 0), SIMD4(0, f, 0, 0),
                              SIMD4(0, 0, far / (near - far), -1), SIMD4(0, 0, near * far / (near - far), 0)))
}
/// The orb's spin, in radians per second of its own time (× tempo). The panel's code block
/// scrolls at this same angular speed (Pave.tourner): one number for both.
let ROTATION_Y: Float = 0.24
private func rotX(_ a: Float) -> float4x4 { float4x4(columns: ([1, 0, 0, 0], [0, cos(a), sin(a), 0], [0, -sin(a), cos(a), 0], [0, 0, 0, 1])) }
private func rotY(_ a: Float) -> float4x4 { float4x4(columns: ([cos(a), 0, -sin(a), 0], [0, 1, 0, 0], [sin(a), 0, cos(a), 0], [0, 0, 0, 1])) }

final class Orbe: NSObject {
    let couche = CAMetalLayer()
    private let dev: MTLDevice, file: MTLCommandQueue, pipe: MTLRenderPipelineState, prof: MTLDepthStencilState
    private let sommets: MTLBuffer, indices: MTLBuffer, nIndices: Int
    private var msaa: MTLTexture?, profondeur: MTLTexture?
    private var u = Uniformes()
    private let cote: Int                     // buffer side in pixels

    // Controls, like orbe.js's `api`
    private(set) var cadence: Double = 60
    var tempo: Double = 1
    private var t: Double = 0, rotY_: Float = 0, rotX_: Float = 0, dernierT = CACurrentMediaTime()
    private var mixT0 = 0.0, transition = false
    private(set) var images = 0
    private var lien: CADisplayLink?, minuteur: Timer?
    private weak var vue: NSView?
    /// Called on every frame with the orb's own elapsed time (real time × tempo): the panel's code block advances there.
    var surImage: ((Double) -> Void)?

    /// `cotePt`: the drawing area's size in points (34 for the pill, like the iframe).
    init(cotePt: CGFloat, echelle: CGFloat, depart: Reglage) {
        dev = MTLCreateSystemDefaultDevice()!
        file = dev.makeCommandQueue()!
        cote = Int((cotePt * min(echelle, 2)).rounded())
        let lib = try! dev.makeLibrary(source: SHADER, options: nil)
        let d = MTLRenderPipelineDescriptor()
        d.vertexFunction = lib.makeFunction(name: "vs"); d.fragmentFunction = lib.makeFunction(name: "fs")
        d.rasterSampleCount = 4                                   // antialias: true
        d.depthAttachmentPixelFormat = .depth32Float
        let c = d.colorAttachments[0]!
        c.pixelFormat = .bgra8Unorm
        // Three r160 NormalBlending: SRC_ALPHA, 1-SRC_ALPHA on colour; ONE, 1-SRC_ALPHA on alpha
        c.isBlendingEnabled = true
        c.sourceRGBBlendFactor = .sourceAlpha; c.destinationRGBBlendFactor = .oneMinusSourceAlpha
        c.sourceAlphaBlendFactor = .one; c.destinationAlphaBlendFactor = .oneMinusSourceAlpha
        pipe = try! dev.makeRenderPipelineState(descriptor: d)
        let ds = MTLDepthStencilDescriptor(); ds.depthCompareFunction = .lessEqual; ds.isDepthWriteEnabled = true
        prof = dev.makeDepthStencilState(descriptor: ds)!
        let (p, i) = icosphere(88)
        sommets = dev.makeBuffer(bytes: p, length: p.count * 4)!
        indices = dev.makeBuffer(bytes: i, length: i.count * 4)!
        nIndices = i.count
        super.init()
        couche.device = dev; couche.pixelFormat = .bgra8Unorm; couche.isOpaque = false
        couche.framebufferOnly = true
        couche.contentsScale = min(echelle, 2)
        couche.drawableSize = CGSize(width: cote, height: cote)
        u.proj = perspective(fovDeg: 42, near: 0.1, far: 100)
        u.uModeA = depart.meca.rawValue; u.uModeB = depart.meca.rawValue
        poser(depart)
        let tx = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .bgra8Unorm, width: cote, height: cote, mipmapped: false)
        tx.textureType = .type2DMultisample; tx.sampleCount = 4; tx.usage = .renderTarget; tx.storageMode = .private
        msaa = dev.makeTexture(descriptor: tx)
        tx.pixelFormat = .depth32Float
        profondeur = dev.makeTexture(descriptor: tx)
    }

    // ── the settings, read and written like Three's uniforms ─────────────────
    private func poser(_ r: Reglage) {
        u.uC1 = lineaire(r.c1); u.uC2 = lineaire(r.c2); u.uC3 = lineaire(r.c3); u.uRim = lineaire(r.rim)
        u.uDisp = Float(r.disp); u.uFreq = Float(r.freq); u.uSpeed = Float(r.speed); u.uRimI = Float(r.rimI)
    }
    /// The glide of colours and material towards the target (orbe.html, k = 0.045 at 30 Hz).
    /// Returns `true` once everything has arrived: the caller then stops its timer.
    func approcher(_ c: Reglage, k: Float = 0.045) -> Bool {
        func l(_ a: Float, _ b: Double) -> Float { a + (Float(b) - a) * k }
        func lc(_ a: SIMD3<Float>, _ b: RGB8) -> SIMD3<Float> { a + (lineaire(b) - a) * k }
        u.uC1 = lc(u.uC1, c.c1); u.uC2 = lc(u.uC2, c.c2); u.uC3 = lc(u.uC3, c.c3); u.uRim = lc(u.uRim, c.rim)
        u.uDisp = l(u.uDisp, c.disp); u.uFreq = l(u.uFreq, c.freq); u.uSpeed = l(u.uSpeed, c.speed); u.uRimI = l(u.uRimI, c.rimI)
        func e(_ a: SIMD3<Float>, _ b: RGB8) -> Float { let d = abs(a - lineaire(b)); return d.x + d.y + d.z }
        let pret = { (a: Float, b: Double) in abs(a - Float(b)) < 0.002 }
        return e(u.uC1, c.c1) + e(u.uC2, c.c2) + e(u.uC3, c.c3) + e(u.uRim, c.rim) < 0.006
            && pret(u.uDisp, c.disp) && pret(u.uFreq, c.freq) && pret(u.uSpeed, c.speed) && pret(u.uRimI, c.rimI)
    }

    func setMecanique(_ m: Mecanique) {
        if m.rawValue == u.uModeB { return }
        if transition { u.uModeA = u.uModeB }
        u.uModeB = m.rawValue; u.uMix = 0
        mixT0 = CACurrentMediaTime(); transition = true
    }
    var enTransition: Bool { transition }
    private func majMix() {
        guard transition else { return }
        let k = min(1, (CACurrentMediaTime() - mixT0) / 1.4)
        u.uMix = Float(k < 0.5 ? 4 * k * k * k : 1 - pow(-2 * k + 2, 3) / 2)
        if k >= 1 { u.uModeA = u.uModeB; u.uMix = 0; transition = false }
    }

    /// The frame rate. Above 10 fps, a CADisplayLink set to the exact rate: the system wakes
    /// the app only for those frames (where Chromium woke it on every refresh to skip
    /// every other one). Below, a timer.
    func setCadence(_ f: Double, vue: NSView) {
        if f == cadence && (lien != nil || minuteur != nil) { return }
        cadence = f; self.vue = vue
        lien?.invalidate(); lien = nil; minuteur?.invalidate(); minuteur = nil
        if f >= 10 {
            let l = vue.displayLink(target: self, selector: #selector(image))
            l.preferredFrameRateRange = CAFrameRateRange(minimum: Float(f), maximum: Float(f), preferred: Float(f))
            l.add(to: .main, forMode: .common); lien = l
        } else {
            let m = Timer(timeInterval: 1 / f, repeats: true) { [weak self] _ in self?.image() }
            m.tolerance = 0.1 / f
            RunLoop.main.add(m, forMode: .common); minuteur = m
        }
    }

    /// No frames at all: a folded panel draws for nobody (orbe.html left it at 1 fps).
    func arreter() {
        lien?.invalidate(); lien = nil; minuteur?.invalidate(); minuteur = nil; cadence = 0
    }

    @objc func image() {
        let now = CACurrentMediaTime()
        let plafond = max(0.05, 3 / max(1, cadence))
        let reel = min(plafond, now - dernierT)
        let dt = tempo * reel; dernierT = now
        surImage?(dt)
        t += dt
        u.uPhase += Float(dt) * u.uSpeed
        majMix()
        rotY_ += Float(dt) * ROTATION_Y; rotX_ += Float(dt) * 0.09
        dessiner()
    }

    func dessiner() {
        guard let d = couche.nextDrawable(), let cb = file.makeCommandBuffer() else { return }
        dessiner(vers: d.texture, cb: cb)
        cb.present(d); cb.commit(); images += 1
    }

    func dessiner(vers cible: MTLTexture, cb: MTLCommandBuffer) {
        let model = rotX(rotX_) * rotY(rotY_)                   // Three's Euler 'XYZ': Rx·Ry·Rz
        var vue = matrix_identity_float4x4; vue.columns.3 = [0, 0, -4.6, 1]
        u.mv = vue * model
        let r = u.mv
        u.nrm = float3x3(columns: (SIMD3(r.columns.0.x, r.columns.0.y, r.columns.0.z),
                                   SIMD3(r.columns.1.x, r.columns.1.y, r.columns.1.z),
                                   SIMD3(r.columns.2.x, r.columns.2.y, r.columns.2.z)))
        let rp = MTLRenderPassDescriptor()
        rp.colorAttachments[0].texture = msaa; rp.colorAttachments[0].resolveTexture = cible
        rp.colorAttachments[0].loadAction = .clear; rp.colorAttachments[0].storeAction = .multisampleResolve
        rp.colorAttachments[0].clearColor = MTLClearColor(red: 0, green: 0, blue: 0, alpha: 0)
        rp.depthAttachment.texture = profondeur; rp.depthAttachment.loadAction = .clear
        rp.depthAttachment.storeAction = .dontCare; rp.depthAttachment.clearDepth = 1
        let e = cb.makeRenderCommandEncoder(descriptor: rp)!
        e.setRenderPipelineState(pipe); e.setDepthStencilState(prof)
        e.setFrontFacing(.counterClockwise); e.setCullMode(.back)   // Three's FrontSide
        e.setVertexBuffer(sommets, offset: 0, index: 0)
        e.setVertexBytes(&u, length: MemoryLayout<Uniformes>.stride, index: 1)
        e.setFragmentBytes(&u, length: MemoryLayout<Uniformes>.stride, index: 1)
        e.drawIndexedPrimitives(type: .triangle, indexCount: nIndices, indexType: .uint32, indexBuffer: indices, indexBufferOffset: 0)
        e.endEncoding()
    }

    /// An off-screen image, to look at the render without a window (checks, comparison).
    func instantane(avance secondes: Double) -> CGImage? {
        let pasN = Int(secondes * 60)
        for _ in 0..<pasN {                                      // advance time at 60 fps, without drawing
            let dt = 1.0 / 60 * tempo
            t += dt; u.uPhase += Float(dt) * u.uSpeed; rotY_ += Float(dt) * ROTATION_Y; rotX_ += Float(dt) * 0.09
        }
        let tx = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .bgra8Unorm, width: cote, height: cote, mipmapped: false)
        tx.usage = [.renderTarget, .shaderRead]; tx.storageMode = .shared
        guard let cible = dev.makeTexture(descriptor: tx), let cb = file.makeCommandBuffer() else { return nil }
        dessiner(vers: cible, cb: cb); cb.commit(); cb.waitUntilCompleted()
        var px = [UInt8](repeating: 0, count: cote * cote * 4)
        cible.getBytes(&px, bytesPerRow: cote * 4, from: MTLRegionMake2D(0, 0, cote, cote), mipmapLevel: 0)
        let ctx = CGContext(data: &px, width: cote, height: cote, bitsPerComponent: 8, bytesPerRow: cote * 4,
                            space: CGColorSpace(name: CGColorSpace.sRGB)!,
                            bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue)
        return ctx?.makeImage()
    }
}
