// Original Dark background. MIT; see the repository LICENSE.
void main() {
    vec2 uv = v_uv;
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    float bend = 0.18 * sin(uv.y * 3.6 + u_time * 0.08);
    float phase = (uv.x * min(aspect, 2.0) + bend + uv.y * 0.12) * 8.0;
    float ribbon = pow(0.5 + 0.5 * cos(phase * 6.283185), 8.0);
    float edge = pow(0.5 + 0.5 * cos((phase + 0.08) * 6.283185), 32.0);
    float light = exp(-3.0 * distance(uv, vec2(0.68, 0.78)));
    float fade = smoothstep(0.05, 0.95, uv.y);
    vec3 color = vec3(0.031) + vec3(0.0, 1.0, 0.533) * (ribbon * 0.24 + edge * 0.16) * light * fade;
    fragColor = vec4(color, 1.0);
}
