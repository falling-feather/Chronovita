import { useEffect, useRef, useState } from 'react';
import type { SolarPresentation } from './sundialModel';

interface SundialSceneProps {
  solar: SolarPresentation;
}

export default function SundialScene({ solar }: SundialSceneProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pointerRef = useRef({ x: 0, y: 0 });
  const [renderState, setRenderState] = useState<'loading' | 'ready' | 'fallback'>('loading');

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return undefined;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (reducedMotion.matches) {
      setRenderState('fallback');
      return undefined;
    }

    let disposed = false;
    let frame = 0;
    let visible = true;
    let cleanup = () => {};

    void import('three').then((THREE) => {
      if (disposed) return;

      try {
        const renderer = new THREE.WebGLRenderer({
          canvas,
          alpha: true,
          antialias: true,
          powerPreference: 'high-performance',
        });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6));
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.08;

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(31, 1, 0.1, 50);
        camera.position.set(0, 2.55, 6.7);
        camera.lookAt(0, -0.05, 0);

        const bronze = new THREE.MeshStandardMaterial({
          color: 0x9a7441,
          metalness: 0.82,
          roughness: 0.36,
        });
        const bronzeLight = new THREE.MeshStandardMaterial({
          color: 0xc8a86a,
          metalness: 0.74,
          roughness: 0.3,
        });
        const patina = new THREE.MeshStandardMaterial({
          color: 0x315f5b,
          metalness: 0.58,
          roughness: 0.58,
        });
        const stone = new THREE.MeshStandardMaterial({
          color: 0x3b4646,
          metalness: 0.05,
          roughness: 0.82,
        });

        const instrument = new THREE.Group();
        instrument.rotation.x = -0.13;
        scene.add(instrument);

        const pedestal = new THREE.Mesh(
          new THREE.CylinderGeometry(2.4, 2.62, 0.46, 96),
          stone,
        );
        pedestal.position.y = -0.55;
        instrument.add(pedestal);

        const lowerBand = new THREE.Mesh(
          new THREE.TorusGeometry(2.35, 0.08, 12, 120),
          patina,
        );
        lowerBand.rotation.x = Math.PI / 2;
        lowerBand.position.y = -0.28;
        instrument.add(lowerBand);

        const dial = new THREE.Mesh(
          new THREE.CylinderGeometry(2.24, 2.24, 0.16, 120),
          bronze,
        );
        dial.position.y = -0.16;
        instrument.add(dial);

        const innerRing = new THREE.Mesh(
          new THREE.TorusGeometry(1.72, 0.028, 10, 120),
          bronzeLight,
        );
        innerRing.rotation.x = Math.PI / 2;
        innerRing.position.y = -0.065;
        instrument.add(innerRing);

        const majorMarkerGeometry = new THREE.BoxGeometry(0.035, 0.035, 0.27);
        const minorMarkerGeometry = new THREE.BoxGeometry(0.022, 0.025, 0.15);
        for (let index = 0; index < 24; index += 1) {
          const angle = (index / 24) * Math.PI * 2;
          const major = index % 2 === 0;
          const marker = new THREE.Mesh(
            major ? majorMarkerGeometry : minorMarkerGeometry,
            index % 6 === 0 ? patina : bronzeLight,
          );
          marker.position.set(Math.sin(angle) * 1.92, -0.055, Math.cos(angle) * 1.92);
          marker.rotation.y = angle;
          instrument.add(marker);
        }

        const gnomonGeometry = new THREE.BufferGeometry();
        gnomonGeometry.setAttribute('position', new THREE.Float32BufferAttribute([
          -0.15, 0, 0.23,
          0.15, 0, 0.23,
          0, 1.48, -0.28,
          0.15, 0, 0.23,
          0, 0, -0.28,
          0, 1.48, -0.28,
        ], 3));
        gnomonGeometry.computeVertexNormals();
        const gnomon = new THREE.Mesh(
          gnomonGeometry,
          new THREE.MeshStandardMaterial({
            color: 0xb79052,
            emissive: 0x38260f,
            emissiveIntensity: 0.4,
            metalness: 0.78,
            roughness: 0.32,
            side: THREE.DoubleSide,
          }),
        );
        gnomon.position.y = -0.04;
        instrument.add(gnomon);

        const centre = new THREE.Mesh(
          new THREE.CylinderGeometry(0.17, 0.2, 0.12, 48),
          patina,
        );
        centre.position.y = -0.02;
        instrument.add(centre);

        scene.add(new THREE.HemisphereLight(0x9bc3c8, 0x171515, 0.92));
        const keyLight = new THREE.DirectionalLight(0xffd89b, solar.lightStrength);
        keyLight.position.set(
          Math.cos(solar.lightAzimuth) * 5.4,
          5.8,
          Math.sin(solar.lightAzimuth) * 5.4,
        );
        scene.add(keyLight);
        const rim = new THREE.PointLight(0x4fa59d, 1.1, 14);
        rim.position.set(-3.6, 1.3, -2.5);
        scene.add(rim);
        const frontFill = new THREE.PointLight(0xd7c49c, 0.72, 15);
        frontFill.position.set(2.8, 3.2, 5.4);
        scene.add(frontFill);

        const resize = () => {
          const { width, height } = host.getBoundingClientRect();
          if (width <= 0 || height <= 0) return;
          renderer.setSize(width, height, false);
          camera.aspect = width / height;
          camera.updateProjectionMatrix();
        };
        resize();

        const resizeObserver = new ResizeObserver(resize);
        resizeObserver.observe(host);
        const intersectionObserver = new IntersectionObserver(([entry]) => {
          visible = entry?.isIntersecting ?? true;
        }, { rootMargin: '120px' });
        intersectionObserver.observe(host);

        const onPointerMove = (event: PointerEvent) => {
          const rect = host.getBoundingClientRect();
          pointerRef.current.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
          pointerRef.current.y = ((event.clientY - rect.top) / rect.height) * 2 - 1;
        };
        const onPointerLeave = () => {
          pointerRef.current.x = 0;
          pointerRef.current.y = 0;
        };
        host.addEventListener('pointermove', onPointerMove, { passive: true });
        host.addEventListener('pointerleave', onPointerLeave, { passive: true });

        let elapsed = 0;
        const render = () => {
          if (disposed) return;
          frame = window.requestAnimationFrame(render);
          if (!visible) return;
          elapsed += 0.008;
          const pointer = pointerRef.current;
          instrument.rotation.y += (pointer.x * 0.095 - instrument.rotation.y) * 0.045;
          instrument.rotation.x += (-0.13 + pointer.y * 0.035 - instrument.rotation.x) * 0.045;
          instrument.position.y = Math.sin(elapsed) * 0.012;
          camera.position.x += (pointer.x * 0.18 - camera.position.x) * 0.035;
          camera.lookAt(0, -0.05, 0);
          renderer.render(scene, camera);
        };
        render();
        setRenderState('ready');

        cleanup = () => {
          window.cancelAnimationFrame(frame);
          resizeObserver.disconnect();
          intersectionObserver.disconnect();
          host.removeEventListener('pointermove', onPointerMove);
          host.removeEventListener('pointerleave', onPointerLeave);
          scene.traverse((object) => {
            if (!(object instanceof THREE.Mesh)) return;
            object.geometry.dispose();
            const materials = Array.isArray(object.material) ? object.material : [object.material];
            materials.forEach((material) => material.dispose());
          });
          renderer.dispose();
        };
      } catch {
        setRenderState('fallback');
      }
    }).catch(() => setRenderState('fallback'));

    return () => {
      disposed = true;
      window.cancelAnimationFrame(frame);
      cleanup();
    };
  }, [solar.lightAzimuth, solar.lightStrength]);

  return (
    <div ref={hostRef} className={`chrono-sundial-scene is-${renderState}`} aria-hidden="true">
      <svg className="chrono-sundial-fallback" viewBox="0 0 720 620" role="presentation">
        <defs>
          <radialGradient id="dial-face" cx="42%" cy="34%" r="66%">
            <stop offset="0" stopColor="#d9bd80" />
            <stop offset="0.55" stopColor="#9a7441" />
            <stop offset="1" stopColor="#4e3926" />
          </radialGradient>
          <filter id="dial-shadow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="22" />
          </filter>
        </defs>
        <ellipse cx="360" cy="486" rx="228" ry="54" fill="#000" opacity=".38" filter="url(#dial-shadow)" />
        <ellipse cx="360" cy="406" rx="236" ry="112" fill="#202c31" stroke="#51615f" strokeWidth="4" />
        <ellipse cx="360" cy="365" rx="210" ry="98" fill="url(#dial-face)" stroke="#bfa066" strokeWidth="5" />
        <ellipse cx="360" cy="365" rx="158" ry="72" fill="none" stroke="#d6bb7c" strokeWidth="3" opacity=".75" />
        <path d="M356 359 L360 166 L382 365 Z" fill="#c8a86a" stroke="#6c512f" strokeWidth="3" />
        <circle cx="360" cy="365" r="15" fill="#315f5b" stroke="#8eb0a8" strokeWidth="3" />
        {Array.from({ length: 12 }, (_, index) => {
          const angle = (index / 12) * Math.PI * 2;
          const x1 = 360 + Math.sin(angle) * 168;
          const y1 = 365 + Math.cos(angle) * 78;
          const x2 = 360 + Math.sin(angle) * 190;
          const y2 = 365 + Math.cos(angle) * 89;
          return <line key={index} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#ead39d" strokeWidth={index % 3 === 0 ? 6 : 3} />;
        })}
      </svg>
      <canvas ref={canvasRef} className="chrono-sundial-canvas" />
    </div>
  );
}
