import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import {
  OrbitControls,
  OrthographicCamera,
  PerspectiveCamera,
  Line,
} from "@react-three/drei";
import {
  Box3,
  BufferGeometry,
  Float32BufferAttribute,
  EdgesGeometry,
  Vector3,
  DoubleSide,
} from "three";
import type { MeshData, MeshPart } from "./types";
import {
  Axis3D,
  Focus,
  Grid3X3,
  Layers,
  Maximize2,
  Ruler,
  Scan,
  X,
} from "lucide-react";

function geometryFor(part: MeshPart) {
  const geometry = new BufferGeometry();
  const raw = (part.positions || part.vertices || []) as number[] | number[][];
  const vertices = Array.isArray(raw[0])
    ? (raw as number[][]).flat()
    : (raw as number[]);
  geometry.setAttribute("position", new Float32BufferAttribute(vertices, 3));
  const faces = (part.indices || part.triangles || []) as number[] | number[][];
  geometry.setIndex(
    Array.isArray(faces[0])
      ? (faces as number[][]).flat()
      : (faces as number[]),
  );
  if (part.normals?.length)
    geometry.setAttribute(
      "normal",
      new Float32BufferAttribute(part.normals, 3),
    );
  else geometry.computeVertexNormals();
  return geometry;
}
function Part({
  part,
  selected,
  ghost,
  offset,
  onSelect,
  onPoint,
}: {
  part: MeshPart;
  selected?: string;
  ghost?: boolean;
  offset: number;
  onSelect: (id: string, part: string, face?: string | number) => void;
  onPoint?: (point: number[], entity?: string) => void;
}) {
  const geometry = useMemo(() => geometryFor(part), [part]);
  const edges = useMemo(() => new EdgesGeometry(geometry, 28), [geometry]);
  useEffect(
    () => () => {
      geometry.dispose();
      edges.dispose();
    },
    [geometry, edges],
  );
  const highlighted =
    selected === part.id ||
    part.faces?.some((face: any) => face.feature_id === selected);
  const color = ghost
    ? "#e8af77"
    : highlighted
      ? "#d9ece8"
      : part.id.toLowerCase().includes("lid")
        ? "#a2c2bb"
        : "#c2cbd0";
  return (
    <group position={[0, 0, offset]}>
      <mesh
        geometry={geometry}
        onClick={(event) => {
          event.stopPropagation();
          const fi = event.faceIndex ?? 0;
          const mapping = part.faces?.find(
            (f: any) =>
              fi >= f.triangle_start &&
              fi < f.triangle_start + f.triangle_count,
          );
          if (onPoint) {
            onPoint(
              event.point.toArray(),
              mapping?.id ? String(mapping.id) : undefined,
            );
            return;
          }
          onSelect(
            mapping?.feature_id || part.triangle_features?.[fi] || part.id,
            part.id,
            mapping?.id ?? part.face_ids?.[fi],
          );
        }}
      >
        <meshStandardMaterial
          color={color}
          metalness={0.35}
          roughness={0.43}
          transparent={ghost}
          opacity={ghost ? 0.25 : 1}
          side={DoubleSide}
          polygonOffset
          polygonOffsetFactor={1}
          polygonOffsetUnits={1}
        />
      </mesh>
      <lineSegments geometry={edges}>
        <lineBasicMaterial
          color={ghost ? "#e8af77" : highlighted ? "#28473e" : "#4a5963"}
          transparent
          opacity={ghost ? 0.45 : 0.75}
        />
      </lineSegments>
    </group>
  );
}
function SceneControls({
  data,
  view,
  fit,
  exploded,
  orthographic,
}: {
  data: MeshData;
  view: string;
  fit: number;
  exploded: boolean;
  orthographic: boolean;
}) {
  const { camera, size: viewSize } = useThree();
  const controls = useRef<any>(null);
  useEffect(() => {
    const bounds = new Box3();
    data.parts.forEach((part) => {
      const g = geometryFor(part);
      g.computeBoundingBox();
      if (g.boundingBox) bounds.union(g.boundingBox);
      g.dispose();
    });
    if (bounds.isEmpty()) return;
    const originalHeight = bounds.getSize(new Vector3()).z;
    if (exploded) {
      bounds.makeEmpty();
      data.parts.forEach((part, i) => {
        const geometry = geometryFor(part);
        geometry.computeBoundingBox();
        if (geometry.boundingBox)
          bounds.union(
            geometry.boundingBox
              .clone()
              .translate(new Vector3(0, 0, i * originalHeight * 1.15)),
          );
        geometry.dispose();
      });
    }
    const center = bounds.getCenter(new Vector3()),
      size = bounds.getSize(new Vector3());
    const halfFov = Math.atan(
      Math.tan((38 * Math.PI) / 360) *
        Math.min(1, viewSize.width / viewSize.height),
    );
    const distance = (size.length() / 2 / Math.sin(halfFov)) * 1.1;
    const directions: Record<string, number[]> = {
      iso: [
        1.1,
        data.parts.length === 1 && data.parts[0].id === "bracket"
          ? 1.35
          : -1.35,
        1,
      ],
      top: [0, -0.001, 1],
      front: [0, -1, 0.001],
      right: [1, 0, 0.001],
    };
    camera.up.set(0, 0, 1);
    camera.position
      .copy(center)
      .add(
        new Vector3(...(directions[view] || directions.iso))
          .normalize()
          .multiplyScalar(distance),
      );
    camera.lookAt(center);
    if ("zoom" in camera && orthographic) {
      camera.zoom =
        Math.min(viewSize.width, viewSize.height) /
        (Math.max(size.x, size.y, size.z) * 1.55);
      camera.updateProjectionMatrix();
    }
    if (controls.current) {
      controls.current.target.copy(center);
      controls.current.update();
    }
  }, [
    camera,
    data,
    view,
    fit,
    exploded,
    orthographic,
    viewSize.width,
    viewSize.height,
  ]);
  return (
    <OrbitControls
      ref={controls}
      makeDefault
      enableDamping
      dampingFactor={0.1}
      minDistance={2}
      maxDistance={2000}
    />
  );
}
export default function Viewport({
  data,
  compare,
  hidden,
  selected,
  onSelect,
  onMeasure,
  loading,
  revisionLabel,
  meshOnly = false,
}: {
  data?: MeshData;
  compare?: MeshData;
  hidden: Set<string>;
  selected?: string;
  onSelect: (id: string, part: string, face?: string | number) => void;
  onMeasure?: (entities: string[], kind: string) => Promise<any>;
  loading?: boolean;
  revisionLabel: string;
  meshOnly?: boolean;
}) {
  const [view, setView] = useState("iso"),
    [fit, setFit] = useState(0),
    [grid, setGrid] = useState(true),
    [axes, setAxes] = useState(true),
    [orthographic, setOrthographic] = useState(false),
    [exploded, setExploded] = useState(false),
    [measure, setMeasure] = useState(false),
    [points, setPoints] = useState<number[][]>([]);
  const [measureKind, setMeasureKind] = useState(
      meshOnly ? "mesh" : "distance",
    ),
    [entities, setEntities] = useState<string[]>([]),
    [measurement, setMeasurement] = useState<any>(),
    [measuring, setMeasuring] = useState(false);
  useEffect(() => {
    function key(event: KeyboardEvent) {
      if (
        event.key.toLowerCase() === "f" &&
        !(
          event.target instanceof HTMLInputElement ||
          event.target instanceof HTMLTextAreaElement ||
          event.target instanceof HTMLSelectElement
        )
      )
        setFit((v) => v + 1);
    }
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  async function pickMeasurement(point: number[], entity?: string) {
    setPoints((prev) => (prev.length >= 2 ? [point] : [...prev, point]));
    if (measureKind === "mesh") return;
    if (!entity) {
      setMeasurement({
        status: "UNKNOWN",
        explanation: "This mesh face has no unique BREP mapping.",
      });
      return;
    }
    const count = measureKind === "area" ? 1 : 2;
    const next = entities.length >= count ? [entity] : [...entities, entity];
    setEntities(next);
    setMeasurement(undefined);
    if (next.length === count && onMeasure) {
      setMeasuring(true);
      try {
        setMeasurement(await onMeasure(next, measureKind));
      } catch (error: any) {
        setMeasurement({ status: "UNKNOWN", explanation: error.message });
      } finally {
        setMeasuring(false);
      }
    }
  }
  const bbox = useMemo(() => {
    const box = new Box3();
    data?.parts.forEach((p) => {
      const g = geometryFor(p);
      g.computeBoundingBox();
      if (g.boundingBox) box.union(g.boundingBox);
      g.dispose();
    });
    return box.isEmpty() ? new Vector3(80, 50, 30) : box.getSize(new Vector3());
  }, [data]);
  const distance =
    points.length === 2
      ? new Vector3(...points[0]).distanceTo(new Vector3(...points[1]))
      : undefined;
  return (
    <section className="viewport" aria-label="3D geometry viewport">
      <div className="viewport-top">
        <span className="viewport-crumb">
          <span className="live-dot" /> {revisionLabel}{" "}
          <span className="subtle">/</span>{" "}
          {orthographic ? "Orthographic" : "Perspective"}
        </span>
        <span className="tag">mm</span>
      </div>
      <div className="viewport-tools">
        <button
          title="Fit model (F)"
          aria-label="Fit model"
          onClick={() => setFit(fit + 1)}
        >
          <Focus size={17} />
        </button>
        <span />
        <button
          className={orthographic ? "active" : ""}
          title="Toggle orthographic projection"
          aria-label="Toggle orthographic projection"
          onClick={() => setOrthographic(!orthographic)}
        >
          <Scan size={17} />
        </button>
        <button
          className={grid ? "active" : ""}
          title="Toggle grid"
          aria-label="Toggle grid"
          onClick={() => setGrid(!grid)}
        >
          <Grid3X3 size={17} />
        </button>
        <button
          className={axes ? "active" : ""}
          title="Toggle axes"
          aria-label="Toggle axes"
          onClick={() => setAxes(!axes)}
        >
          <Axis3D size={17} />
        </button>
        <button
          className={exploded ? "active" : ""}
          title="Explode preview"
          aria-label="Explode preview"
          onClick={() => setExploded(!exploded)}
        >
          <Layers size={17} />
        </button>
        <span />
        <button
          className={measure ? "active" : ""}
          title="Measure between two surface points"
          aria-label="Measure geometry"
          onClick={() => {
            setMeasure(!measure);
            setPoints([]);
            if (!measure) setExploded(false);
          }}
        >
          <Ruler size={17} />
        </button>
      </div>
      {data && (
        <Canvas
          frameloop="demand"
          shadows
          camera={{
            position: [130, -150, 130],
            near: 0.1,
            far: 10000,
            up: [0, 0, 1],
          }}
          gl={{ antialias: true }}
          onPointerMissed={() => onSelect("", "")}
        >
          <color attach="background" args={["#20252b"]} />
          {orthographic ? (
            <OrthographicCamera
              makeDefault
              position={[130, -150, 130]}
              near={0.1}
              far={10000}
              up={[0, 0, 1]}
            />
          ) : (
            <PerspectiveCamera
              makeDefault
              fov={38}
              position={[130, -150, 130]}
              near={0.1}
              far={10000}
              up={[0, 0, 1]}
            />
          )}
          <ambientLight intensity={1.1} />
          <hemisphereLight args={["#dfebe9", "#55545a", 1.4]} />
          <directionalLight position={[80, -120, 200]} intensity={3.2} />
          <directionalLight
            position={[-120, 80, 100]}
            intensity={1.4}
            color="#acc4e8"
          />
          {grid && (
            <gridHelper
              args={[600, 60, "#39434e", "#2d353e"]}
              rotation={[Math.PI / 2, 0, 0]}
              position={[0, 0, -0.15]}
            />
          )}
          {axes && <axesHelper args={[Math.max(bbox.x, bbox.y) * 0.65]} />}
          <Suspense fallback={null}>
            {data.parts
              .filter((p) => !hidden.has(p.id))
              .map((p, i) => (
                <Part
                  key={p.id}
                  part={p}
                  selected={selected}
                  offset={exploded ? i * bbox.z * 1.15 : 0}
                  onSelect={onSelect}
                  onPoint={measure ? pickMeasurement : undefined}
                />
              ))}
          </Suspense>
          {compare?.parts.map((p) => (
            <Part
              key={"compare-" + p.id}
              part={p}
              ghost
              offset={0}
              onSelect={onSelect}
            />
          ))}
          {points.length === 2 && (
            <Line
              points={points as [number, number, number][]}
              color="#ffbd87"
              lineWidth={2}
            />
          )}{" "}
          {points.map((p, i) => (
            <mesh key={i} position={p as [number, number, number]}>
              <sphereGeometry args={[0.7, 12, 12]} />
              <meshBasicMaterial color="#ffbd87" />
            </mesh>
          ))}
          <SceneControls
            data={data}
            view={view}
            fit={fit}
            exploded={exploded}
            orthographic={orthographic}
          />
        </Canvas>
      )}
      {!data && (
        <div className="viewport-empty">
          <Maximize2 size={32} />
          <h3>
            {loading ? "Building your geometry…" : "Your next part starts here"}
          </h3>
          <p>
            {loading
              ? "Compiling source, exporting STEP, and measuring the result."
              : "Choose a starting recipe from the project library."}
          </p>
        </div>
      )}
      {exploded && (
        <div className="preview-note">
          <Layers size={13} /> Exploded preview · exports use assembly positions
        </div>
      )}
      {measure && (
        <div className="measurement-hint">
          <Ruler size={15} />
          <select
            aria-label="Measurement kind"
            value={measureKind}
            onChange={(e) => {
              setMeasureKind(e.target.value);
              setPoints([]);
              setEntities([]);
              setMeasurement(undefined);
            }}
          >
            {!meshOnly && (
              <>
                <option value="distance">BREP face distance</option>
                <option value="angle">BREP face angle</option>
                <option value="area">BREP face area</option>
              </>
            )}
            <option value="mesh">Mesh point distance</option>
          </select>
          <span>
            {measuring
              ? "Measuring reopened STEP…"
              : measureKind === "mesh"
                ? distance !== undefined
                  ? `${distance.toFixed(3)} mm · approximate`
                  : points.length === 1
                    ? "Select a second point"
                    : "Select two surface points"
                : measurement
                  ? measurement.status === "PASS"
                    ? `${Number(measurement.actual).toFixed(3)} ${measurement.unit} · ${measurement.method}`
                    : `${measurement.status}: ${measurement.explanation}`
                  : measureKind === "area"
                    ? "Select a BREP face"
                    : entities.length
                      ? "Select a second BREP face"
                      : "Select two BREP faces"}
          </span>
          <button
            aria-label="Close measurement"
            onClick={() => {
              setMeasure(false);
              setPoints([]);
              setEntities([]);
              setMeasurement(undefined);
            }}
          >
            <X size={14} />
          </button>
        </div>
      )}
      <div className="view-presets">
        {["iso", "top", "front", "right"].map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={view === v ? "active" : ""}
          >
            {v === "iso" ? "Isometric" : v[0].toUpperCase() + v.slice(1)}
          </button>
        ))}
      </div>
      <div className="orbit-hint">
        Drag to orbit <span>·</span> Shift + drag to pan <span>·</span> Scroll
        to zoom
      </div>
      <div className="axis-legend">
        <b className="axis-z">Z</b>
        <b className="axis-y">Y</b>
        <b className="axis-x">X</b>
      </div>
    </section>
  );
}
