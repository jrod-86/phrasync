"""Read-only broad-phase footprint audit of visible landmark prototypes."""
import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

from qa_scene import DevTools, chrome_path, websocket_url


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:5510')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='karaokesesh-footprint-',ignore_cleanup_errors=True) as profile:
        browser=subprocess.Popen([str(chrome_path()),'--headless=new','--no-first-run',
            '--remote-debugging-port=9238','--remote-allow-origins=*','--window-size=960,620',
            f'--user-data-dir={profile}',args.url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        dev=None
        try:
            dev=DevTools(websocket_url(9238));time.sleep(2)
            dev.eval("""(async()=>{window.__vfExportMode=true;
              document.body.innerHTML='<canvas id="audit"></canvas>';
              await import('/static/scene3d-gl.js');window.auditScene=VFSceneGL.get(document.querySelector('canvas'));
              auditScene.setSize(960,540);})()""")
            result=[]
            for kit in ['japan','china','italy','usa']:
                dev.eval(f'auditScene.build({json.dumps(kit)})')
                for seed in [1337,2026,881]:
                    for direction,t in [(d,t) for d in ['forward','left','right'] for t in [0,7.25,43.8]]:
                        dev.eval(f'auditScene.update({t},{{seed:{seed},direction:{json.dumps(direction)},density:1,pulse:1,environment:{{daytime:"day",season:"summer",weather:"clear"}}}});auditScene.render()')
                        record=dev.eval("""(()=>{
                            const T=VFSceneGL.THREE; auditScene.scene.updateMatrixWorld(true);
                            const boxes=[];
                            for(const [index,holder] of (auditScene.slots||[]).entries()) {
                              if(!holder.visible)continue;
                              const active=(holder.userData.variants||[]).find(v=>v.visible);
                              if(!active)continue;
                              const box=new T.Box3().setFromObject(active);if(box.isEmpty())continue;
                              const size=box.getSize(new T.Vector3());
                              boxes.push({index,box,size:[size.x,size.y,size.z],center:box.getCenter(new T.Vector3()).toArray()});
                            }
                            const overlaps=[];
                            for(let a=0;a<boxes.length;a++)for(let b=a+1;b<boxes.length;b++){
                              if(boxes[a].box.intersectsBox(boxes[b].box))overlaps.push([boxes[a].index,boxes[b].index]);
                            }
                            const architectureOverlaps=[];
                            for(const name of ['facades','cornices','awnings','eaves','walls']) {
                              const batch=auditScene.world?.batches?.[name];if(!batch?.visible)continue;
                              batch.geometry.computeBoundingBox();
                              for(let i=0;i<batch.count;i++){
                                const matrix=new T.Matrix4();batch.getMatrixAt(i,matrix);
                                matrix.premultiply(batch.matrixWorld);
                                const box=batch.geometry.boundingBox.clone().applyMatrix4(matrix);
                                for(const landmark of boxes)if(box.intersectsBox(landmark.box))architectureOverlaps.push([landmark.index,name,i]);
                              }
                            }
                            return {visible:boxes.length,overlaps,architectureOverlaps,
                              maxWidth:Math.max(0,...boxes.map(b=>b.size[0])),maxDepth:Math.max(0,...boxes.map(b=>b.size[2])),
                              boxes:boxes.map(({box,...b})=>b)};
                        })()""")
                        result.append({'kit':kit,'seed':seed,'time':t,'direction':direction,**record})
            out=Path('qa_out/landmark-footprints.json');out.parent.mkdir(exist_ok=True)
            out.write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps({'cases':len(result),'casesWithBroadPhaseOverlap':sum(bool(r['overlaps']) for r in result),
                'casesWithArchitectureOverlap':sum(bool(r['architectureOverlaps']) for r in result),
                'maxDepth':max(r['maxDepth'] for r in result),'report':str(out.resolve()),
                'caveat':'Visible landmark AABBs vs other landmarks and facade/cornice/awning instances; open arches can produce conservative false positives; foliage and ground-contact intentionally not treated as collisions.'}))
        finally:
            if dev:dev.close()
            browser.terminate();browser.wait(timeout=15)


if __name__=='__main__':main()
