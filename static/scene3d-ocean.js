/* Original procedural ocean for KaraokeSesh. No downloaded textures or assets.
 * A world-space water surface and atmospheric sky share one full-screen pass.
 * Only playback time drives motion, keeping preview, seeking and export equal.
 */

const vertexShader = `
varying vec2 vScreen;
void main() {
  vScreen = position.xy;
  gl_Position = vec4(position.xy, 0.99999, 1.0);
}`;

const fragmentShader = `
precision highp float;
varying vec2 vScreen;
uniform float uTime, uAspect, uTanFov, uNight, uDay, uWaves, uClouds;
uniform vec3 uOrigin, uSun, uMoon;
uniform mat3 uRotation;

float hash(vec2 p) {
  vec3 q = fract(vec3(p.xyx) * vec3(.1031, .1030, .0973));
  q += dot(q, q.yzx + 33.33);
  return fract((q.x + q.y) * q.z);
}
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  f = f*f*(3.0-2.0*f);
  return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);
}
float fbm(vec2 p) {
  float n=0.0, a=.5;
  mat2 r=mat2(.8,-.6,.6,.8);
  for(int i=0;i<5;i++) { n+=a*noise(p); p=r*p*2.03+vec2(17.1,9.2); a*=.49; }
  return n;
}

vec3 sky(vec3 ray, bool disk) {
  float h = max(ray.y,0.0);
  vec3 horizon = mix(vec3(.16,.095,.073),vec3(.50,.69,.84),uDay);
  vec3 zenith = mix(vec3(.075,.071,.095),vec3(.065,.26,.51),uDay);
  horizon = mix(horizon,vec3(.035,.063,.115),uNight);
  zenith = mix(zenith,vec3(.004,.009,.026),uNight);
  vec3 col = mix(horizon,zenith,pow(clamp(h,0.0,1.0),.45));
  float sunDot=clamp(dot(ray,uSun),-1.0,1.0);
  float glow=exp((sunDot-1.0)*6.0);
  col+=vec3(1.6,.33,.009)*glow*.63*(1.0-uDay*.93)*(1.0-uNight);
  col+=vec3(2.0,.75,.018)*exp((sunDot-1.0)*85.0)*.48*(1.0-uDay)*(1.0-uNight);
  if(disk) {
    float sunDisk=smoothstep(.99980,.99990,sunDot);
    col+=mix(vec3(5.0,2.8,1.0),vec3(5.0,4.6,3.6),uDay)*sunDisk*(1.0-uNight);
    col+=vec3(1.0,.51,.23)*exp((sunDot-1.0)*360.0)*.18*(1.0-uNight);
    float moonDot=dot(ray,uMoon);
    col+=vec3(.77,.88,1.0)*smoothstep(.99976,.99984,moonDot)*2.0*uNight;
    col+=vec3(.10,.16,.27)*exp((moonDot-1.0)*160.0)*uNight;
  }
  if(uNight>.01 && ray.y>0.025) {
    vec2 stars=vec2(atan(ray.z,ray.x),asin(clamp(ray.y,-1.0,1.0)))*390.0;
    vec2 cell=floor(stars), point=fract(stars)-.5;
    float seed=hash(cell);
    float star=(1.0-smoothstep(.015,.12,length(point)))*step(.994,seed);
    col+=vec3(.60,.72,.91)*star*uNight*smoothstep(.025,.20,ray.y);
  }
  // A cloud sheet at physical altitude; no screen-space stripes or moving UV sky.
  if(ray.y>.015) {
    vec2 p=ray.xz/(ray.y+.15)*1.8+uOrigin.xz*.0004;
    p+=vec2(uTime*.004,uTime*.0015);
    float broad=fbm(p*.72);
    float detail=fbm(p*2.4+vec2(broad*2.0));
    float density=smoothstep(.37,.66,broad*.73+detail*.27)*uClouds;
    vec3 lit=mix(vec3(1.1,.35,.036),vec3(.90,.95,1.0),uDay);
    vec3 shade=mix(vec3(.075,.065,.08),vec3(.45,.59,.72),uDay);
    vec3 cloud=mix(shade,lit,clamp(glow*.8+detail*.55,0.0,1.0));
    cloud=mix(cloud,vec3(.04,.065,.105)+glow*.025,uNight);
    col=mix(col,cloud,density*smoothstep(.015,.12,ray.y)*.82);
  }
  return col;
}

// Analytic multiscale wave elevation and gradient. Incommensurate directions
// avoid regular parallel stripes, and fine detail fades before subpixel aliasing.
vec3 surface(vec2 p, float footprint) {
  vec3 wave=vec3(0.0);
  p+=vec2(sin(dot(p,vec2(.017,.024))),sin(dot(p,vec2(-.021,.013))))*4.0;
  float frequency=.26, amplitude=.38;
  vec2 d=normalize(vec2(.83,.56));
  mat2 turn=mat2(.57,-.822,.822,.57);
  for(int i=0;i<11;i++) {
    float fi=float(i);
    float resolved=1.0-smoothstep(.7,2.5,frequency*footprint);
    float phase=dot(p,d)*frequency+uTime*sqrt(9.81*frequency)*(mod(fi,2.0)*2.0-1.0)+fi*2.173;
    float crest=sin(phase), slope=cos(phase);
    wave.x+=amplitude*crest*resolved;
    wave.yz+=amplitude*frequency*slope*d*resolved;
    p+=d*crest*.16;
    frequency*=1.73; amplitude*=.48; d=turn*d;
  }
  return wave*uWaves;
}

void main() {
  // Same symmetric perspective projection as the real Three.js lyric camera.
  vec3 ray=normalize(uRotation*vec3(vScreen.x*uAspect*uTanFov,vScreen.y*uTanFov,-1.0));
  vec3 color;
  if(ray.y>=-.0008) {
    color=sky(ray,true);
  } else {
    float distanceToWater=min(35000.0,uOrigin.y/max(-ray.y,.0008));
    // Height intersection uses the same world-space surface as the normal.
    // The near field therefore shows real wave relief as the camera travels.
    for(int j=0;j<4;j++) {
      vec3 p=uOrigin+ray*distanceToWater;
      float height=surface(p.xz,max(.03,distanceToWater*.0012)).x;
      float estimate=(uOrigin.y-height)/max(-ray.y,.0008);
      distanceToWater=mix(distanceToWater,clamp(estimate,.1,35000.0),.6);
    }
    vec3 point=uOrigin+ray*distanceToWater;
    vec2 flatPoint=uOrigin.xz+ray.xz*(uOrigin.y/max(-ray.y,.0008));
    float footprint=max(.018,max(length(dFdx(flatPoint)),length(dFdy(flatPoint)))*1.05);
    vec3 wave=surface(point.xz,footprint);
    wave*=1.0-smoothstep(700.0,4000.0,distanceToWater);
    vec2 ripples=vec2(noise(point.xz*1.8),noise(point.zx*2.3+18.0))-.5;
    wave.yz+=ripples*.12*uWaves*(1.0-smoothstep(.2,.8,footprint));
    vec3 normal=normalize(vec3(-wave.y,1.0,-wave.z));
    vec3 reflection=reflect(ray,normal);
    reflection.y=max(.002,reflection.y);
    reflection=normalize(reflection);
    float fresnel=.025+.975*pow(1.0-max(0.0,dot(normal,-ray)),5.0);
    vec3 depth=mix(vec3(.0015,.026,.045),vec3(.012,.16,.21),uDay);
    depth=mix(depth,vec3(.002,.010,.021),uNight);
    vec3 reflectedSky=sky(reflection,false)*mix(.58,1.0,max(uDay,uNight));
    color=mix(depth,reflectedSky,clamp(fresnel,.04,.97));
    vec3 light=normalize(mix(uSun,uMoon,uNight));
    vec3 halfVector=normalize(light-ray);
    float nh=max(.001,dot(normal,halfVector));
    float nv=max(.025,dot(normal,-ray));
    float nl=max(.0,dot(normal,light));
    float rough=.115+min(.065,footprint*.004);
    float a2=rough*rough;
    float divisor=nh*nh*(a2-1.0)+1.0;
    float distribution=a2/(3.14159265*divisor*divisor);
    float glint=distribution*nl/(4.0*nv+.45);
    vec3 sunlight=mix(vec3(1.0,.31,.012),vec3(1.0,.93,.77),uDay);
    sunlight=mix(sunlight,vec3(.32,.49,.72),uNight);
    color+=sunlight*glint*.58;
    // Small bright, irregular crests in foreground; no uniform white foam layer.
    float crest=smoothstep(.43,.77,wave.x)*smoothstep(.23,.57,length(wave.yz));
    color+=mix(vec3(.12,.13,.13),vec3(.17,.27,.28),uDay)*crest*exp(-distanceToWater*.018);
    float haze=1.0-exp(-distanceToWater*.00017);
    color=mix(color,sky(normalize(vec3(ray.x,.003,ray.z)),false),haze*.7);
    float horizonBlend=smoothstep(-.002,-.0008,ray.y);
    color=mix(color,sky(ray,true),horizonBlend);
  }
  // Filmic response preserves the sunset reflection while retaining sea detail.
  color=max(vec3(0.0),color);
  color=(color*(2.51*color+.03))/(color*(2.43*color+.59)+.14);
  color=pow(clamp(color,0.0,1.0),vec3(1.0/2.2));
  gl_FragColor=vec4(color,1.0);
}`;

export function createOcean(THREE) {
  const uniforms = {
    uTime: { value: 0 }, uAspect: { value: 16 / 9 }, uTanFov: { value: .60 },
    uNight: { value: 0 }, uDay: { value: 0 }, uWaves: { value: 1 }, uClouds: { value: 1 },
    uOrigin: { value: new THREE.Vector3(0, 4.2, 0) },
    uRotation: { value: new THREE.Matrix3() },
    uSun: { value: new THREE.Vector3() }, uMoon: { value: new THREE.Vector3() },
  };
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute([-1, -1, 0, 3, -1, 0, -1, 3, 0], 3));
  const material = new THREE.ShaderMaterial({ uniforms, vertexShader, fragmentShader, depthWrite: false, depthTest: false, fog: false, toneMapped: false });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.frustumCulled = false;
  mesh.renderOrder = -10000;
  const group = new THREE.Group();
  group.name = "Lost in the Ocean";
  group.add(mesh);
  return { group, mesh, material, uniforms };
}

function celestial(THREE, target, azimuth, elevation) {
  const az = THREE.MathUtils.degToRad(azimuth), el = THREE.MathUtils.degToRad(elevation);
  target.set(Math.sin(az) * Math.cos(el), Math.sin(el), -Math.cos(az) * Math.cos(el));
}

export function updateOcean(THREE, ocean, options = {}) {
  if (!ocean) return;
  const { t = 0, camera, environment = {},
    sunAzimuth = 25, sunElevation = 12, moonAzimuth = -25, moonElevation = 18, waveStrength = 1 } = options;
  const u = ocean.uniforms;
  const daytime = typeof environment === "string" ? environment : environment.daytime;
  u.uTime.value = Number(t) || 0;
  const blend = THREE.MathUtils.clamp(Number(environment.dayMix ?? environment.dayBlend) || 0, 0, 1);
  const dayValue = value => ["day", "noon", "midday", "morning"].includes(value) ? 1 : 0;
  u.uNight.value = THREE.MathUtils.lerp(daytime === "night" ? 1 : 0, environment.nextDaytime === "night" ? 1 : 0, blend);
  u.uDay.value = THREE.MathUtils.lerp(dayValue(daytime), dayValue(environment.nextDaytime), blend);
  u.uWaves.value = THREE.MathUtils.clamp(Number(waveStrength) || .01, .01, 2.5);
  u.uClouds.value = environment.weather === "storm" ? 2 : environment.weather === "cloudy" ? 1.5 : .8;
  celestial(THREE, u.uSun.value, sunAzimuth, sunElevation);
  celestial(THREE, u.uMoon.value, moonAzimuth, moonElevation);
  if (camera) {
    camera.updateMatrixWorld();
    u.uAspect.value = camera.aspect || 16 / 9;
    u.uTanFov.value = Math.tan(THREE.MathUtils.degToRad(camera.fov || 62) / 2);
    u.uRotation.value.setFromMatrix4(camera.matrixWorld);
    u.uOrigin.value.setFromMatrixPosition(camera.matrixWorld);
  }
}

// The ocean and lyrics must never invent different camera paths or horizons.
// Keep longitudinal travel identical to the lyric clock; bounded directional
// excursions and secondary motion act on the actual camera, not shader UVs.
export function updateOceanCamera(camera, t, options = {}) {
  const { speed = 9, direction = "forward", secondaryMotion = "none", motionAmount = .35 } = options;
  const amount = Math.max(0, Math.min(1, Number(motionAmount) || 0));
  const lateral = direction === "left" ? -1 : direction === "right" ? 1 : 0;
  const vertical = ["up", "ascend"].includes(direction) ? 1 : ["down", "dive"].includes(direction) ? -1 : 0;
  let x = lateral * Math.sin(t * .12) * 1.6;
  let y = 4.2 + vertical * Math.sin(t * .12) * 1.3;
  let roll = 0;
  if (["drift", "bank"].includes(direction)) x += Math.sin(t * .24) * 1.6;
  if (direction === "bank") roll = Math.sin(t * .19) * .04;
  if (["sway", "orbit"].includes(secondaryMotion)) x += Math.sin(t * .17) * amount * 1.5;
  if (["rise", "float"].includes(secondaryMotion)) y += Math.sin(t * .23) * amount * .7;
  if (secondaryMotion === "orbit") {
    y += (Math.cos(t * .17) - 1) * amount * .35;
    roll += Math.sin(t * .17) * amount * .025;
  }
  camera.position.set(x, y, -t * speed);
  camera.rotation.set(-Math.atan(.15), 0, roll);
}
