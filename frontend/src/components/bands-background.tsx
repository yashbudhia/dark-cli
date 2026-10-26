"use client";

import { useEffect, useRef } from "react";

const vertexSource = `#version 300 es
in vec2 a_position;
out vec2 v_uv;
void main() {
  v_uv = a_position * 0.5 + 0.5;
  gl_Position = vec4(a_position, 0.0, 1.0);
}`;

const fragmentHeader = `#version 300 es
precision highp float;
precision highp int;
in vec2 v_uv;
out vec4 fragColor;
uniform vec2 u_resolution;
uniform float u_time;
uniform vec4 u_colors[8];
uniform int u_colors_length;
uniform float u_seed, u_speed, u_ephemeralAmp, u_lensScale;
uniform float u_lensSpacingX, u_lensSpacingY, u_lensRadius;
uniform float u_dispersionStrength, u_edgeDisp;
`;

export function BandsBackground() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl2", {
      alpha: false,
      antialias: false,
      powerPreference: "low-power",
    });
    if (!gl) return;
    const controller = new AbortController();
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let visible = true;
    let time = 0;
    let previous = 0;
    let program: WebGLProgram | null = null;
    let buffer: WebGLBuffer | null = null;
    const shaders: WebGLShader[] = [];

    function compile(type: number, source: string) {
      const shader = gl!.createShader(type);
      if (!shader) throw new Error("Shader unavailable");
      shaders.push(shader);
      gl!.shaderSource(shader, source);
      gl!.compileShader(shader);
      if (!gl!.getShaderParameter(shader, gl!.COMPILE_STATUS))
        throw new Error("Shader compilation failed");
      return shader;
    }

    function draw(now: number) {
      if (!program || controller.signal.aborted || !visible || document.hidden)
        return;
      const bounds = canvas!.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio, 1.5);
      const width = Math.max(1, Math.round(bounds.width * ratio));
      const height = Math.max(1, Math.round(bounds.height * ratio));
      if (canvas!.width !== width || canvas!.height !== height) {
        canvas!.width = width;
        canvas!.height = height;
        gl!.viewport(0, 0, width, height);
      }
      if (previous) time += Math.min((now - previous) / 1000, 0.05);
      previous = now;
      gl!.uniform2f(
        gl!.getUniformLocation(program, "u_resolution"),
        width,
        height,
      );
      gl!.uniform1f(gl!.getUniformLocation(program, "u_time"), time);
      gl!.drawArrays(gl!.TRIANGLES, 0, 6);
      canvas!.dataset.ready = "true";
      if (!reducedMotion.matches) frame = requestAnimationFrame(draw);
    }

    function resume() {
      cancelAnimationFrame(frame);
      previous = 0;
      if (visible && !document.hidden) frame = requestAnimationFrame(draw);
    }

    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      resume();
    });
    observer.observe(canvas);
    document.addEventListener("visibilitychange", resume);
    reducedMotion.addEventListener("change", resume);
    window.addEventListener("resize", resume);
    function lost(event: Event) {
      event.preventDefault();
      cancelAnimationFrame(frame);
      canvas!.dataset.ready = "false";
    }
    canvas.addEventListener("webglcontextlost", lost);

    async function start() {
      try {
        const response = await fetch("/framer/shaders/bands.frag", {
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Shader source unavailable");
        const fragment = await response.text();
        if (controller.signal.aborted) return;
        program = gl!.createProgram();
        if (!program) throw new Error("WebGL program unavailable");
        gl!.attachShader(program, compile(gl!.VERTEX_SHADER, vertexSource));
        gl!.attachShader(
          program,
          compile(gl!.FRAGMENT_SHADER, fragmentHeader + fragment),
        );
        gl!.linkProgram(program);
        if (!gl!.getProgramParameter(program, gl!.LINK_STATUS))
          throw new Error("Shader linking failed");
        gl!.useProgram(program);
        buffer = gl!.createBuffer();
        gl!.bindBuffer(gl!.ARRAY_BUFFER, buffer);
        gl!.bufferData(
          gl!.ARRAY_BUFFER,
          new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
          gl!.STATIC_DRAW,
        );
        const position = gl!.getAttribLocation(program, "a_position");
        gl!.enableVertexAttribArray(position);
        gl!.vertexAttribPointer(position, 2, gl!.FLOAT, false, 0, 0);
        gl!.uniform4fv(
          gl!.getUniformLocation(program, "u_colors[0]"),
          new Float32Array([
            0,
            1,
            136 / 255,
            1,
            17 / 255,
            17 / 255,
            17 / 255,
            1,
            8 / 255,
            8 / 255,
            8 / 255,
            1,
          ]),
        );
        gl!.uniform1i(gl!.getUniformLocation(program, "u_colors_length"), 3);
        // Values read directly from the user's Framer Shader Background Layer.
        const uniforms = {
          u_seed: 210,
          u_speed: 0.3,
          u_ephemeralAmp: 0,
          u_lensScale: 3.7,
          u_lensSpacingX: 1,
          u_lensSpacingY: 0.01,
          u_lensRadius: 0.41,
          u_dispersionStrength: 0,
          u_edgeDisp: 0,
        };
        for (const [name, value] of Object.entries(uniforms))
          gl!.uniform1f(gl!.getUniformLocation(program, name), value);
        resume();
      } catch {
        // The original Framer fallback image stays visible if WebGL is unavailable.
        canvas!.dataset.ready = "false";
      }
    }
    void start();
    return () => {
      controller.abort();
      cancelAnimationFrame(frame);
      observer.disconnect();
      document.removeEventListener("visibilitychange", resume);
      reducedMotion.removeEventListener("change", resume);
      window.removeEventListener("resize", resume);
      canvas.removeEventListener("webglcontextlost", lost);
      if (buffer) gl.deleteBuffer(buffer);
      if (program) gl.deleteProgram(program);
      shaders.forEach((shader) => gl.deleteShader(shader));
    };
  }, []);

  return (
    <div className="bands-background" aria-hidden="true">
      <canvas ref={ref} />
    </div>
  );
}
