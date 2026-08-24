import { useEffect, useRef, useState } from 'react';
import type { SolarPresentation } from './sundialModel';

interface ChronoscopeSceneProps {
  solar: SolarPresentation;
  activeEra: number;
}

const ERA_ACCENTS = [0x63a69d, 0xb96c45, 0xc49a57, 0xd5b66f, 0x76a69a, 0xa98249] as const;

export default function ChronoscopeScene({ solar, activeEra }: ChronoscopeSceneProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pointerRef = useRef({ x: 0, y: 0 });
  const solarRef = useRef(solar);
  const eraRef = useRef(activeEra);
  const [renderState, setRenderState] = useState<'loading' | 'ready' | 'fallback'>('loading');

  useEffect(() => {
    solarRef.current = solar;
  }, [solar]);

  useEffect(() => {
    eraRef.current = activeEra;
  }, [activeEra]);

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
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.55));
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.02;
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFShadowMap;

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 60);
        camera.position.set(0, 1.05, 9.45);
        camera.lookAt(0, -0.18, 0);

        const textures: Array<{ dispose: () => void }> = [];
        const environmentCanvas = document.createElement('canvas');
        environmentCanvas.width = 256;
        environmentCanvas.height = 128;
        const environmentContext = environmentCanvas.getContext('2d');
        if (!environmentContext) throw new Error('environment texture canvas is unavailable');
        const skyGradient = environmentContext.createLinearGradient(0, 0, 0, 128);
        skyGradient.addColorStop(0, '#f2d8a2');
        skyGradient.addColorStop(0.38, '#607c7d');
        skyGradient.addColorStop(0.72, '#172126');
        skyGradient.addColorStop(1, '#090d10');
        environmentContext.fillStyle = skyGradient;
        environmentContext.fillRect(0, 0, 256, 128);
        const keyGlow = environmentContext.createRadialGradient(58, 34, 2, 58, 34, 42);
        keyGlow.addColorStop(0, 'rgba(255, 236, 183, .96)');
        keyGlow.addColorStop(1, 'rgba(255, 210, 125, 0)');
        environmentContext.fillStyle = keyGlow;
        environmentContext.fillRect(0, 0, 128, 96);
        const environmentTexture = new THREE.CanvasTexture(environmentCanvas);
        environmentTexture.mapping = THREE.EquirectangularReflectionMapping;
        environmentTexture.colorSpace = THREE.SRGBColorSpace;
        scene.environment = environmentTexture;
        textures.push(environmentTexture);

        const createDialTexture = () => {
          const textureCanvas = document.createElement('canvas');
          textureCanvas.width = 1024;
          textureCanvas.height = 1024;
          const context = textureCanvas.getContext('2d');
          if (!context) throw new Error('dial texture canvas is unavailable');

          const centre = 512;
          const gradient = context.createRadialGradient(410, 350, 48, centre, centre, 510);
          gradient.addColorStop(0, '#d7bb79');
          gradient.addColorStop(0.42, '#a57c43');
          gradient.addColorStop(0.78, '#76542f');
          gradient.addColorStop(1, '#3c2d24');
          context.fillStyle = gradient;
          context.fillRect(0, 0, 1024, 1024);

          let seed = 19;
          for (let index = 0; index < 2400; index += 1) {
            seed = (seed * 48271) % 2147483647;
            const x = seed % 1024;
            seed = (seed * 48271) % 2147483647;
            const y = seed % 1024;
            seed = (seed * 48271) % 2147483647;
            const alpha = 0.018 + (seed % 17) / 1500;
            context.fillStyle = seed % 3 === 0
              ? `rgba(42, 103, 93, ${alpha})`
              : `rgba(32, 21, 13, ${alpha})`;
            context.fillRect(x, y, 1 + (seed % 3), 1 + (seed % 3));
          }

          context.save();
          context.translate(centre, centre);
          context.strokeStyle = 'rgba(45, 34, 23, .66)';
          context.lineWidth = 5;
          [116, 232, 344, 430].forEach((radius) => {
            context.beginPath();
            context.arc(0, 0, radius, 0, Math.PI * 2);
            context.stroke();
          });
          context.strokeStyle = 'rgba(233, 205, 139, .66)';
          context.lineWidth = 2;
          for (let index = 0; index < 48; index += 1) {
            const angle = (index / 48) * Math.PI * 2;
            const inner = index % 4 === 0 ? 350 : 380;
            context.beginPath();
            context.moveTo(Math.sin(angle) * inner, -Math.cos(angle) * inner);
            context.lineTo(Math.sin(angle) * 426, -Math.cos(angle) * 426);
            context.stroke();
          }
          context.fillStyle = 'rgba(242, 216, 159, .82)';
          context.font = '600 42px "Noto Serif SC", "Songti SC", serif';
          context.textAlign = 'center';
          context.textBaseline = 'middle';
          ['先', '秦', '汉', '唐', '宋', '明'].forEach((label, index) => {
            const angle = (index / 6) * Math.PI * 2;
            context.save();
            context.rotate(angle);
            context.fillText(label, 0, -292);
            context.restore();
          });
          context.restore();

          const texture = new THREE.CanvasTexture(textureCanvas);
          texture.colorSpace = THREE.SRGBColorSpace;
          texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 8);
          textures.push(texture);
          return texture;
        };

        const dialTexture = createDialTexture();
        const bronze = new THREE.MeshStandardMaterial({
          color: 0x85572b,
          metalness: 0.68,
          roughness: 0.3,
          envMapIntensity: 0.78,
        });
        const bronzeHighlight = new THREE.MeshStandardMaterial({
          color: 0xb1813c,
          emissive: 0x241304,
          emissiveIntensity: 0.16,
          metalness: 0.66,
          roughness: 0.24,
          envMapIntensity: 0.86,
        });
        const patina = new THREE.MeshStandardMaterial({
          color: 0x205a52,
          metalness: 0.58,
          roughness: 0.48,
          envMapIntensity: 0.66,
        });
        const stone = new THREE.MeshStandardMaterial({
          color: 0x2a3231,
          metalness: 0.04,
          roughness: 0.88,
          envMapIntensity: 0.4,
        });
        const dialFace = new THREE.MeshStandardMaterial({
          color: 0xb48750,
          map: dialTexture,
          bumpMap: dialTexture,
          bumpScale: 0.025,
          emissive: 0x76512a,
          emissiveMap: dialTexture,
          emissiveIntensity: 0.62,
          metalness: 0.32,
          roughness: 0.4,
          envMapIntensity: 0.46,
        });

        const root = new THREE.Group();
        root.position.y = -0.08;
        scene.add(root);

        const base = new THREE.Mesh(
          new THREE.CylinderGeometry(2.6, 2.86, 0.46, 112),
          stone,
        );
        base.position.y = -1.4;
        base.receiveShadow = true;
        root.add(base);

        const baseStep = new THREE.Mesh(
          new THREE.CylinderGeometry(2.34, 2.52, 0.2, 112),
          bronze,
        );
        baseStep.position.y = -1.08;
        baseStep.castShadow = true;
        baseStep.receiveShadow = true;
        root.add(baseStep);

        for (const radius of [2.05, 2.25]) {
          const baseRing = new THREE.Mesh(
            new THREE.TorusGeometry(radius, radius === 2.25 ? 0.07 : 0.035, 12, 128),
            radius === 2.25 ? patina : bronzeHighlight,
          );
          baseRing.rotation.x = Math.PI / 2;
          baseRing.position.y = -0.94;
          baseRing.castShadow = true;
          root.add(baseRing);
        }

        const supportGeometry = new THREE.BoxGeometry(0.24, 1.66, 0.34, 2, 8, 2);
        for (const side of [-1, 1]) {
          const support = new THREE.Mesh(supportGeometry, bronze);
          support.position.set(side * 1.92, -0.12, 0);
          support.rotation.z = side * -0.13;
          support.castShadow = true;
          root.add(support);
          const joint = new THREE.Mesh(
            new THREE.CylinderGeometry(0.2, 0.2, 0.42, 48),
            patina,
          );
          joint.position.set(side * 1.86, 0.55, 0.02);
          joint.rotation.z = Math.PI / 2;
          joint.castShadow = true;
          root.add(joint);
        }

        const armillary = new THREE.Group();
        armillary.position.y = 0.34;
        armillary.rotation.set(-0.14, -0.12, -0.06);
        root.add(armillary);

        const outerRing = new THREE.Mesh(
          new THREE.TorusGeometry(2.08, 0.095, 18, 160),
          bronze,
        );
        outerRing.castShadow = true;
        armillary.add(outerRing);

        const meridianRing = new THREE.Mesh(
          new THREE.TorusGeometry(1.85, 0.056, 14, 144),
          bronzeHighlight,
        );
        meridianRing.rotation.set(0.2, 0.72, 0.04);
        meridianRing.castShadow = true;
        armillary.add(meridianRing);

        const horizonRing = new THREE.Mesh(
          new THREE.TorusGeometry(1.72, 0.052, 14, 144),
          patina,
        );
        horizonRing.rotation.x = Math.PI / 2;
        horizonRing.castShadow = true;
        armillary.add(horizonRing);

        const dial = new THREE.Mesh(
          new THREE.CylinderGeometry(1.58, 1.58, 0.16, 128),
          [bronze, dialFace, bronze],
        );
        dial.rotation.x = Math.PI / 2;
        dial.rotation.z = -0.08;
        dial.position.z = 0.04;
        dial.castShadow = true;
        dial.receiveShadow = true;
        armillary.add(dial);

        for (const radius of [1.16, 1.4, 1.58]) {
          const ring = new THREE.Mesh(
            new THREE.TorusGeometry(radius, radius === 1.58 ? 0.045 : 0.018, 10, 128),
            radius === 1.58 ? bronzeHighlight : patina,
          );
          ring.position.z = 0.115;
          ring.castShadow = true;
          armillary.add(ring);
        }

        const markerGeometry = new THREE.BoxGeometry(0.025, 0.17, 0.035);
        for (let index = 0; index < 36; index += 1) {
          const angle = (index / 36) * Math.PI * 2;
          const marker = new THREE.Mesh(
            markerGeometry,
            index % 6 === 0 ? bronzeHighlight : patina,
          );
          marker.position.set(Math.sin(angle) * 1.47, Math.cos(angle) * 1.47, 0.145);
          marker.rotation.z = -angle;
          marker.castShadow = true;
          armillary.add(marker);
        }

        const gnomonShape = new THREE.Shape();
        gnomonShape.moveTo(-0.13, -0.6);
        gnomonShape.lineTo(0.13, -0.6);
        gnomonShape.lineTo(0.02, 0.55);
        gnomonShape.lineTo(-0.13, -0.6);
        const gnomon = new THREE.Mesh(
          new THREE.ExtrudeGeometry(gnomonShape, {
            depth: 0.1,
            bevelEnabled: true,
            bevelSegments: 2,
            bevelSize: 0.025,
            bevelThickness: 0.025,
          }),
          bronzeHighlight,
        );
        gnomon.position.z = 0.16;
        gnomon.castShadow = true;
        armillary.add(gnomon);

        const solarHand = new THREE.Mesh(
          new THREE.BoxGeometry(0.035, 1.34, 0.04),
          new THREE.MeshStandardMaterial({
            color: 0x39251a,
            metalness: 0.7,
            roughness: 0.36,
          }),
        );
        solarHand.position.z = 0.36;
        solarHand.castShadow = true;
        armillary.add(solarHand);

        const centreHub = new THREE.Mesh(
          new THREE.CylinderGeometry(0.16, 0.2, 0.18, 48),
          patina,
        );
        centreHub.rotation.x = Math.PI / 2;
        centreHub.position.z = 0.25;
        centreHub.castShadow = true;
        armillary.add(centreHub);

        const dustGeometry = new THREE.BufferGeometry();
        const dustPositions = new Float32Array(130 * 3);
        let dustSeed = 31;
        for (let index = 0; index < dustPositions.length; index += 1) {
          dustSeed = (dustSeed * 16807) % 2147483647;
          const normalized = dustSeed / 2147483647;
          const axis = index % 3;
          dustPositions[index] = axis === 0
            ? (normalized - 0.5) * 7.2
            : axis === 1
              ? normalized * 4.8 - 1.7
              : (normalized - 0.5) * 4.6;
        }
        dustGeometry.setAttribute('position', new THREE.BufferAttribute(dustPositions, 3));
        const dustMaterial = new THREE.PointsMaterial({
          color: 0xd4b879,
          size: 0.022,
          transparent: true,
          opacity: 0.24,
          depthWrite: false,
        });
        const dust = new THREE.Points(dustGeometry, dustMaterial);
        scene.add(dust);

        scene.add(new THREE.HemisphereLight(0xa8d2d0, 0x1c120e, 0.7));
        scene.add(new THREE.AmbientLight(0xffdca4, 0.2));
        const keyLight = new THREE.DirectionalLight(
          0xffd8a0,
          0.42 + solarRef.current.lightStrength * 0.92,
        );
        keyLight.castShadow = true;
        keyLight.shadow.mapSize.set(1024, 1024);
        keyLight.shadow.camera.left = -5;
        keyLight.shadow.camera.right = 5;
        keyLight.shadow.camera.top = 5;
        keyLight.shadow.camera.bottom = -5;
        scene.add(keyLight);
        const eraLight = new THREE.PointLight(ERA_ACCENTS[activeEra] ?? ERA_ACCENTS[0], 6.5, 14, 1.8);
        eraLight.position.set(-3.2, 1.6, 2.4);
        scene.add(eraLight);
        const frontFill = new THREE.DirectionalLight(0xffe4ae, 1.45);
        frontFill.position.set(3.2, 3.3, 5.2);
        scene.add(frontFill);
        const lowerFill = new THREE.DirectionalLight(0x79afa6, 0.55);
        lowerFill.position.set(-2.5, -1.2, 3.8);
        scene.add(lowerFill);

        const shadow = new THREE.Mesh(
          new THREE.PlaneGeometry(7.2, 5.2),
          new THREE.ShadowMaterial({ color: 0x000000, opacity: 0.3 }),
        );
        shadow.rotation.x = -Math.PI / 2;
        shadow.position.y = -1.64;
        shadow.receiveShadow = true;
        scene.add(shadow);

        const resize = () => {
          const { width, height } = host.getBoundingClientRect();
          if (width <= 0 || height <= 0) return;
          renderer.setSize(width, height, false);
          camera.aspect = width / height;
          camera.position.z = width / height < 1 ? 10.4 : 9.45;
          camera.updateProjectionMatrix();
        };
        resize();

        const resizeObserver = new ResizeObserver(resize);
        resizeObserver.observe(host);
        const intersectionObserver = new IntersectionObserver(([entry]) => {
          visible = entry?.isIntersecting ?? true;
        }, { rootMargin: '80px' });
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
          if (!visible || document.hidden) return;
          elapsed += 0.008;
          const pointer = pointerRef.current;
          const currentSolar = solarRef.current;
          const currentEra = Math.max(0, Math.min(ERA_ACCENTS.length - 1, eraRef.current));
          const targetRotation = pointer.x * 0.09 + (currentEra - 2.5) * 0.012;
          root.rotation.y += (targetRotation - root.rotation.y) * 0.035;
          root.rotation.x += ((-0.025 + pointer.y * 0.028) - root.rotation.x) * 0.035;
          root.position.y = -0.08 + Math.sin(elapsed) * 0.008;
          armillary.rotation.y = -0.12 + Math.sin(elapsed * 0.42) * 0.015;
          meridianRing.rotation.z = 0.04 + Math.sin(elapsed * 0.31) * 0.018;
          solarHand.rotation.z = -currentSolar.lightAzimuth + Math.PI / 2;
          keyLight.intensity = 0.42 + currentSolar.lightStrength * 0.92;
          keyLight.position.set(
            Math.cos(currentSolar.lightAzimuth) * 5.8,
            5.6,
            Math.sin(currentSolar.lightAzimuth) * 5.8,
          );
          eraLight.color.setHex(ERA_ACCENTS[currentEra]);
          dust.rotation.y = elapsed * 0.008;
          camera.position.x += (pointer.x * 0.28 - camera.position.x) * 0.035;
          camera.position.y += ((1.05 - pointer.y * 0.12) - camera.position.y) * 0.035;
          camera.lookAt(0, -0.18, 0);
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
            if (!(object instanceof THREE.Mesh || object instanceof THREE.Points)) return;
            object.geometry.dispose();
            const materials = Array.isArray(object.material) ? object.material : [object.material];
            materials.forEach((material) => material.dispose());
          });
          textures.forEach((texture) => texture.dispose());
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
  }, []);

  return (
    <div ref={hostRef} className={`chrono-sundial-scene chrono-chronoscope-scene is-${renderState}`} aria-hidden="true">
      <svg className="chrono-sundial-fallback chrono-chronoscope-fallback" viewBox="0 0 840 700" role="presentation">
        <defs>
          <radialGradient id="chrono-face" cx="40%" cy="30%" r="72%">
            <stop offset="0" stopColor="#ddc487" />
            <stop offset=".48" stopColor="#a47a43" />
            <stop offset="1" stopColor="#473326" />
          </radialGradient>
          <linearGradient id="chrono-stone" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0" stopColor="#4b5553" />
            <stop offset="1" stopColor="#192123" />
          </linearGradient>
          <filter id="chrono-shadow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="24" />
          </filter>
        </defs>
        <ellipse cx="430" cy="594" rx="282" ry="62" fill="#000" opacity=".38" filter="url(#chrono-shadow)" />
        <ellipse cx="430" cy="546" rx="278" ry="94" fill="url(#chrono-stone)" stroke="#77817e" strokeWidth="5" />
        <ellipse cx="430" cy="515" rx="242" ry="74" fill="#89653a" stroke="#d2b170" strokeWidth="5" />
        <g transform="translate(430 332) rotate(-7)">
          <circle r="214" fill="none" stroke="#a98249" strokeWidth="22" />
          <ellipse rx="194" ry="78" fill="none" stroke="#4f8b82" strokeWidth="10" transform="rotate(-8)" />
          <ellipse rx="96" ry="198" fill="none" stroke="#c5a15f" strokeWidth="9" transform="rotate(28)" />
          <circle r="154" fill="url(#chrono-face)" stroke="#dfc17f" strokeWidth="8" />
          <circle r="126" fill="none" stroke="#3b6c67" strokeWidth="4" />
          <circle r="96" fill="none" stroke="#e6cc91" strokeWidth="3" opacity=".78" />
          {Array.from({ length: 24 }, (_, index) => {
            const angle = (index / 24) * Math.PI * 2;
            const x1 = Math.sin(angle) * 132;
            const y1 = -Math.cos(angle) * 132;
            const x2 = Math.sin(angle) * 148;
            const y2 = -Math.cos(angle) * 148;
            return <line key={index} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#f0d79c" strokeWidth={index % 4 === 0 ? 6 : 3} />;
          })}
          <path d="M-14 55 L13 55 L2 -92 Z" fill="#caaa68" stroke="#4b3522" strokeWidth="4" />
          <circle r="18" fill="#356d67" stroke="#8fb5a8" strokeWidth="4" />
        </g>
        <path d="M238 490 L264 224" stroke="#a98249" strokeWidth="18" strokeLinecap="round" />
        <path d="M622 490 L600 228" stroke="#a98249" strokeWidth="18" strokeLinecap="round" />
        <circle cx="266" cy="262" r="19" fill="#356d67" stroke="#caaa68" strokeWidth="7" />
        <circle cx="599" cy="263" r="19" fill="#356d67" stroke="#caaa68" strokeWidth="7" />
      </svg>
      <canvas ref={canvasRef} className="chrono-sundial-canvas chrono-chronoscope-canvas" />
    </div>
  );
}
