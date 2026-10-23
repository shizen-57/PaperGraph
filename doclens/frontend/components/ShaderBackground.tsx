"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

const VERTEX_SHADER = `attribute vec2 a_position;
void main() {
  gl_Position = vec4(a_position, 0.0, 1.0);
}`;

const FRAGMENT_SHADER = `precision highp float;
uniform vec2 u_resolution;

vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec2 mod289(vec2 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec3 permute(vec3 x) { return mod289(((x * 34.0) + 1.0) * x); }

float snoise(vec2 v) {
  const vec4 C = vec4(0.211324865405187, 0.366025403784439, -0.577350269189626, 0.024390243902439);
  vec2 i = floor(v + dot(v, C.yy));
  vec2 x0 = v - i + dot(i, C.xx);
  vec2 i1 = x0.x > x0.y ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
  vec4 x12 = x0.xyxy + C.xxzz;
  x12.xy -= i1;
  i = mod289(i);
  vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));
  vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)), 0.0);
  m *= m;
  m *= m;
  vec3 x = 2.0 * fract(p * C.www) - 1.0;
  vec3 h = abs(x) - 0.5;
  vec3 a0 = x - floor(x + 0.5);
  m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);
  vec3 g;
  g.x = a0.x * x0.x + h.x * x0.y;
  g.yz = a0.yz * x12.xz + h.yz * x12.yw;
  return 130.0 * dot(m, g);
}

float hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

void main() {
  vec2 st = gl_FragCoord.xy / u_resolution.xy;
  vec2 uv = st;
  uv.x *= u_resolution.x / u_resolution.y;
  vec2 mouseOffset = vec2(0.0);
  float t = 0.0;
  float n1 = snoise((uv + mouseOffset) * 1.15 + vec2(cos(t * 0.65), sin(t * 0.45)) * 0.7);
  float n2 = snoise((uv - mouseOffset * 0.5) * 1.85 - vec2(sin(t * 0.55), cos(t * 0.75)) * 0.55 + n1 * 0.75);
  float n3 = snoise(uv * 2.8 + vec2(t * 0.25, -t * 0.2) + n2 * 0.65);
  float n4 = snoise(uv * 4.2 - vec2(t * 0.35, t * 0.3) + n3 * 0.4);

  vec3 base = vec3(0.08, 0.07, 0.13);
  vec3 col = vec3(0.96, 0.94, 0.91) * 0.62 + base * 0.38;
  float wYellow = smoothstep(-0.25, 0.75, n1);
  float wPink = smoothstep(-0.35, 0.65, n2);
  float wCyan = smoothstep(-0.2, 0.8, n3);
  float wViolet = smoothstep(-0.4, 0.7, n4);
  float wRed = smoothstep(0.1, 0.9, n2 * n3);
  float wGreen = smoothstep(0.2, 0.85, n1 * n4);
  col = mix(col, vec3(1.0, 0.86, 0.28), wYellow * 0.55);
  col = mix(col, vec3(0.98, 0.34, 0.52), wPink * 0.48 * (1.0 - wYellow * 0.4));
  col = mix(col, vec3(0.24, 0.68, 0.94), wCyan * 0.45);
  col = mix(col, vec3(0.48, 0.28, 0.82), wViolet * 0.42);
  col = mix(col, vec3(0.78, 0.15, 0.22), wRed * 0.38);
  col = mix(col, vec3(0.28, 0.78, 0.46), wGreen * 0.32);

  float vignette = smoothstep(1.45, 0.35, length((st - 0.5) * vec2(1.15, 1.0)));
  col = mix(base * 0.75, col, vignette * 0.86 + 0.14);
  float timeJitter = 0.0;
  float fineGrain = hash21(gl_FragCoord.xy + vec2(timeJitter * 97.13, timeJitter * 43.19)) - 0.5;
  float paperGrain = hash21(floor(gl_FragCoord.xy * 0.5) + vec2(timeJitter * 13.7, -timeJitter * 19.3)) - 0.5;
  col += (fineGrain * 0.16 + paperGrain * 0.10) * (0.8 + 0.4 * length(col));
  gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}`;

export default function ShaderBackground() {
  const pathname = usePathname();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const isHome = pathname === "/";

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (isHome && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      video.play().catch(() => {});
      return;
    }
    // Keep the outgoing video alive until its crossfade finishes.
    const pause = window.setTimeout(() => video.pause(), isHome ? 0 : 900);
    return () => window.clearTimeout(pause);
  }, [isHome]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const gl = canvas?.getContext("webgl", { alpha: false, antialias: false, powerPreference: "low-power" });
    if (!canvas || !gl) return;

    const compile = (type: number, source: string) => {
      const shader = gl.createShader(type);
      if (!shader) return null;
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        gl.deleteShader(shader);
        return null;
      }
      return shader;
    };

    const vertex = compile(gl.VERTEX_SHADER, VERTEX_SHADER);
    const fragment = compile(gl.FRAGMENT_SHADER, FRAGMENT_SHADER);
    if (!vertex || !fragment) {
      if (vertex) gl.deleteShader(vertex);
      if (fragment) gl.deleteShader(fragment);
      return;
    }
    const program = gl.createProgram();
    if (!program) {
      gl.deleteShader(vertex);
      gl.deleteShader(fragment);
      return;
    }
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    gl.deleteShader(vertex);
    gl.deleteShader(fragment);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      gl.deleteProgram(program);
      return;
    }

    const buffer = gl.createBuffer();
    if (!buffer) {
      gl.deleteProgram(program);
      return;
    }
    gl.useProgram(program);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, "a_position");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

    const resolution = gl.getUniformLocation(program, "u_resolution");
    const resize = () => {
      const scale = Math.min(window.devicePixelRatio || 1, 1.25);
      canvas.width = Math.max(1, Math.round(canvas.clientWidth * scale));
      canvas.height = Math.max(1, Math.round(canvas.clientHeight * scale));
      gl.viewport(0, 0, canvas.width, canvas.height);
      if (resolution) gl.uniform2f(resolution, canvas.width, canvas.height);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    return () => {
      observer.disconnect();
      gl.deleteBuffer(buffer);
      gl.deleteProgram(program);
    };
  }, []);

  return (
    <div className="ambient-background" data-home={isHome} aria-hidden="true">
      <canvas ref={canvasRef} />
      <video ref={videoRef} className="ambient-video" src="/bg_static.mp4" poster="/bg.jpg" preload="none" muted loop playsInline />
    </div>
  );
}
