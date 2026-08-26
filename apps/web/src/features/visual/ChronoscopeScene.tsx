import { useEffect, useRef, useState } from 'react';
import { publicAssetUrl } from '../../runtime';

type RenderState = 'loading' | 'webgpu' | 'webgl2' | 'fallback';

interface ChronoscopeSceneProps {
  onReady?: (state: Exclude<RenderState, 'loading'>) => void;
}

const MAP_ROOT = publicAssetUrl('/assets/home-chronodial');

export default function ChronoscopeScene({ onReady }: ChronoscopeSceneProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const readyCallbackRef = useRef(onReady);
  const [renderState, setRenderState] = useState<RenderState>('loading');

  useEffect(() => {
    readyCallbackRef.current = onReady;
  }, [onReady]);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return undefined;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (reducedMotion.matches) {
      setRenderState('fallback');
      readyCallbackRef.current?.('fallback');
      return undefined;
    }

    let disposed = false;
    let cleanup = () => {};

    void import('three/webgpu').then(async (THREE) => {
      if (disposed) return;
      try {
        const renderer = new THREE.WebGPURenderer({
          canvas,
          alpha: true,
          antialias: true,
          samples: 4,
        });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.65));
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.08;
        await renderer.init();
        if (disposed) {
          renderer.dispose();
          return;
        }

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 40);
        camera.position.set(0, 0.3, 7.4);

        const loader = new THREE.TextureLoader();
        const [albedo, bump, roughness] = await Promise.all([
          loader.loadAsync(`${MAP_ROOT}/chronodial-albedo-1024.webp`),
          loader.loadAsync(`${MAP_ROOT}/chronodial-bump-1024.webp`),
          loader.loadAsync(`${MAP_ROOT}/chronodial-roughness-1024.webp`),
        ]);
        if (disposed) {
          albedo.dispose();
          bump.dispose();
          roughness.dispose();
          renderer.dispose();
          return;
        }
        albedo.colorSpace = THREE.SRGBColorSpace;
        bump.colorSpace = THREE.NoColorSpace;
        roughness.colorSpace = THREE.NoColorSpace;
        for (const texture of [albedo, bump, roughness]) texture.anisotropy = 8;

        const bronzeEdge = new THREE.MeshStandardMaterial({
          color: 0x72502f,
          metalness: 0.9,
          roughness: 0.28,
        });
        const dialFace = new THREE.MeshStandardMaterial({
          color: 0xffffff,
          map: albedo,
          bumpMap: bump,
          bumpScale: 0.14,
          roughnessMap: roughness,
          roughness: 0.68,
          metalness: 0.76,
        });
        const dialBack = new THREE.MeshStandardMaterial({
          color: 0x211913,
          metalness: 0.74,
          roughness: 0.58,
        });
        const brightBronze = new THREE.MeshStandardMaterial({
          color: 0xd4aa63,
          emissive: 0x2b1604,
          emissiveIntensity: 0.2,
          metalness: 0.94,
          roughness: 0.18,
        });
        const jade = new THREE.MeshStandardMaterial({
          color: 0x2d8a78,
          emissive: 0x08261f,
          emissiveIntensity: 0.24,
          metalness: 0.26,
          roughness: 0.2,
        });

        const root = new THREE.Group();
        root.rotation.x = -0.24;
        root.rotation.z = -0.04;
        scene.add(root);

        const disc = new THREE.Mesh(
          new THREE.CylinderGeometry(2.32, 2.32, 0.2, 192, 1, false),
          [bronzeEdge, dialFace, dialBack],
        );
        disc.rotation.x = Math.PI / 2;
        root.add(disc);

        const outerRing = new THREE.Mesh(
          new THREE.TorusGeometry(2.39, 0.065, 20, 192),
          brightBronze,
        );
        outerRing.position.z = 0.12;
        root.add(outerRing);

        const bearing = new THREE.Mesh(
          new THREE.SphereGeometry(0.2, 48, 32),
          jade,
        );
        bearing.scale.z = 0.46;
        bearing.position.z = 0.2;
        root.add(bearing);

        const handPivot = new THREE.Group();
        handPivot.position.z = 0.29;
        root.add(handPivot);
        const hand = new THREE.Mesh(
          new THREE.BoxGeometry(0.055, 1.76, 0.055),
          brightBronze,
        );
        hand.position.y = 0.88;
        handPivot.add(hand);
        const handTip = new THREE.Mesh(
          new THREE.SphereGeometry(0.07, 24, 16),
          brightBronze,
        );
        handTip.position.y = 1.72;
        handPivot.add(handTip);

        const lightSweep = new THREE.PointLight(0xffd58d, 34, 12, 2.1);
        lightSweep.position.set(-3.4, 2.8, 4.2);
        scene.add(lightSweep);
        const rim = new THREE.DirectionalLight(0x67c7b5, 2.1);
        rim.position.set(3.5, -1.2, 3.8);
        scene.add(rim);
        scene.add(new THREE.HemisphereLight(0xd7e7e1, 0x17100c, 1.4));

        const resize = () => {
          const { width, height } = host.getBoundingClientRect();
          if (width <= 0 || height <= 0) return;
          renderer.setSize(width, height, false);
          camera.aspect = width / height;
          camera.position.z = width / height < 1 ? 8.8 : 7.4;
          camera.updateProjectionMatrix();
        };
        resize();
        const resizeObserver = new ResizeObserver(resize);
        resizeObserver.observe(host);

        const start = performance.now();
        renderer.setAnimationLoop((time) => {
          if (disposed || document.hidden) return;
          const elapsed = Math.max(0, (time - start) / 1000);
          const turnProgress = Math.min(1, elapsed / 1.05);
          const eased = 1 - ((1 - turnProgress) ** 4);
          handPivot.rotation.z = (-Math.PI * 5.75) * (1 - eased);
          root.rotation.y = Math.sin(elapsed * 0.44) * 0.028;
          root.position.y = Math.sin(elapsed * 0.8) * 0.018;
          lightSweep.position.x = -3.4 + Math.min(1, elapsed / 1.5) * 6.8;
          renderer.render(scene, camera);
        });

        const backend = renderer.backend as { isWebGPUBackend?: boolean };
        const state: Exclude<RenderState, 'loading'> = backend.isWebGPUBackend ? 'webgpu' : 'webgl2';
        setRenderState(state);
        readyCallbackRef.current?.(state);

        cleanup = () => {
          resizeObserver.disconnect();
          renderer.setAnimationLoop(null);
          scene.traverse((object) => {
            if (!(object instanceof THREE.Mesh)) return;
            object.geometry.dispose();
            const materials = Array.isArray(object.material) ? object.material : [object.material];
            materials.forEach((material) => material.dispose());
          });
          albedo.dispose();
          bump.dispose();
          roughness.dispose();
          renderer.dispose();
        };
      } catch {
        if (disposed) return;
        setRenderState('fallback');
        readyCallbackRef.current?.('fallback');
      }
    }).catch(() => {
      if (disposed) return;
      setRenderState('fallback');
      readyCallbackRef.current?.('fallback');
    });

    return () => {
      disposed = true;
      cleanup();
    };
  }, []);

  return (
    <div
      ref={hostRef}
      className={`chrono-chronodial-scene is-${renderState}`}
      data-renderer={renderState}
      aria-hidden="true"
    >
      <div className="chrono-chronodial-fallback">
        <img src={`${MAP_ROOT}/chronodial-albedo-1024.webp`} alt="" />
        <span className="chrono-chronodial-fallback-hand" />
      </div>
      <canvas ref={canvasRef} className="chrono-chronodial-canvas" />
    </div>
  );
}
