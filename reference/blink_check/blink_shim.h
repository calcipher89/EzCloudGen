// A tiny C++ stand-in for the BlinkScript language, so a kernel can be compiled and run on the
// CPU without Nuke: catches syntax errors and lets reference renders be compared. Not Nuke's
// compiler; Nuke may still reject something this accepts.
#pragma once
#include <cmath>
#include <algorithm>

struct float2 { float x, y; float2(float v = 0) : x(v), y(v) {} float2(float a, float b) : x(a), y(b) {} };
struct float3 {
  float x, y, z;
  float3(float v = 0) : x(v), y(v), z(v) {}
  float3(float a, float b, float c) : x(a), y(b), z(c) {}
};
struct float4 {
  float x, y, z, w;
  float4(float v = 0) : x(v), y(v), z(v), w(v) {}
  float4(float a, float b, float c, float d) : x(a), y(b), z(c), w(d) {}
};
struct int2 { int x, y; };

#define OP3(op) \
  inline float3 operator op(float3 a, float3 b) { return float3(a.x op b.x, a.y op b.y, a.z op b.z); } \
  inline float3 operator op(float3 a, float b) { return float3(a.x op b, a.y op b, a.z op b); } \
  inline float3 operator op(float a, float3 b) { return float3(a op b.x, a op b.y, a op b.z); }
OP3(+) OP3(-) OP3(*) OP3(/)
#define OP4(op) \
  inline float4 operator op(float4 a, float4 b) { return float4(a.x op b.x, a.y op b.y, a.z op b.z, a.w op b.w); } \
  inline float4 operator op(float4 a, float b) { return float4(a.x op b, a.y op b, a.z op b, a.w op b); }
OP4(+) OP4(-) OP4(*) OP4(/)
inline float3 &operator+=(float3 &a, float3 b) { a = a + b; return a; }
inline float4 &operator+=(float4 &a, float4 b) { a = a + b; return a; }
inline float dot(float3 a, float3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
inline float length(float3 a) { return std::sqrt(dot(a, a)); }
inline float3 normalize(float3 a) { return a / length(a); }
inline float3 cross(float3 a, float3 b) { return float3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x); }
inline float clamp(float v, float a, float b) { return std::min(std::max(v, a), b); }
using std::min; using std::max; using std::floor; using std::sqrt; using std::exp; using std::pow;
using std::fabs; using std::cos; using std::sin; using std::log;

enum { ePixelWise };
enum { eRead, eWrite };
enum { eAccessPoint, eAccessRandom };
enum { eEdgeClamped };

struct Recti {
  int x1 = 0, y1 = 0, x2 = 0, y2 = 0;
  int width() const { return x2 - x1; }
  int height() const { return y2 - y1; }
};

// Point images: the kernel reads src() / writes dst() at the current pixel. A random access
// image also holds pixels (rgba floats, rows going up) for bilinear(); edges clamp.
template <int... A> struct Image {
  float4 value;
  Recti bounds;
  const float *pix = nullptr;
  float4 &operator()() { return value; }
  float4 at(int x, int y) const {
    x = std::min(std::max(x, bounds.x1), bounds.x2 - 1) - bounds.x1;
    y = std::min(std::max(y, bounds.y1), bounds.y2 - 1) - bounds.y1;
    const float *q = pix + (y * bounds.width() + x) * 4;
    return float4(q[0], q[1], q[2], q[3]);
  }
};
template <int... A> inline float4 bilinear(const Image<A...> &im, float x, float y) {
  if (!im.pix) return float4(0.0f);
  float fx = std::floor(x), fy = std::floor(y);
  float ax = x - fx, ay = y - fy;
  int ix = int(fx), iy = int(fy);
  float4 a = im.at(ix, iy), b = im.at(ix + 1, iy), c = im.at(ix, iy + 1), d = im.at(ix + 1, iy + 1);
  return (a * (1 - ax) + b * ax) * (1 - ay) + (c * (1 - ax) + d * ax) * ay;
}
template <int M> struct ImageComputationKernel {};
template <class T> inline void defineParamImpl(T &v, const char *, T d) { v = d; }
#define defineParam(v, name, d) defineParamImpl(v, name, decltype(v)(d))
