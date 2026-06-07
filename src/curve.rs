//! TRUSTED. Short-Weierstrass curve y^2 = x^3 + a*x + b over F_p, affine coords.
//!
//! This is the *real* group the oracle serves. The contestant never sees these
//! coordinates — only opaque tokens (see `oracle.rs`). Coordinates are published
//! separately in `instance.public.json` for the (unscored) representation-attack
//! research track described in the README.

use crate::field;

/// Affine point, or the point at infinity (the group identity).
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub struct Point {
    pub inf: bool,
    pub x: u64,
    pub y: u64,
}

impl Point {
    pub fn infinity() -> Self {
        Point { inf: true, x: 0, y: 0 }
    }
    pub fn affine(x: u64, y: u64) -> Self {
        Point { inf: false, x, y }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Curve {
    pub p: u64,
    pub a: u64,
    pub b: u64,
}

impl Curve {
    pub fn new(p: u64, a: u64, b: u64) -> Self {
        Curve { p, a, b }
    }

    /// Nonsingular iff discriminant 4a^3 + 27b^2 != 0 (mod p).
    pub fn is_nonsingular(&self) -> bool {
        let p = self.p;
        let a3 = field::mul(field::mul(self.a, self.a, p), self.a, p);
        let four_a3 = field::mul(4, a3, p);
        let b2 = field::mul(self.b, self.b, p);
        let twenty_seven_b2 = field::mul(27, b2, p);
        field::add(four_a3, twenty_seven_b2, p) != 0
    }

    pub fn on_curve(&self, pt: &Point) -> bool {
        if pt.inf {
            return true;
        }
        let p = self.p;
        let lhs = field::mul(pt.y, pt.y, p);
        let x2 = field::mul(pt.x, pt.x, p);
        let x3 = field::mul(x2, pt.x, p);
        let ax = field::mul(self.a, pt.x, p);
        let rhs = field::add(field::add(x3, ax, p), self.b, p);
        lhs == rhs
    }

    pub fn neg(&self, pt: &Point) -> Point {
        if pt.inf {
            return *pt;
        }
        Point::affine(pt.x, field::neg(pt.y, self.p))
    }

    /// Affine point addition (handles doubling and the identity).
    pub fn add(&self, p1: &Point, p2: &Point) -> Point {
        if p1.inf {
            return *p2;
        }
        if p2.inf {
            return *p1;
        }
        let p = self.p;
        if p1.x == p2.x {
            // Either P == -Q  -> infinity, or P == Q -> doubling.
            if field::add(p1.y, p2.y, p) == 0 {
                return Point::infinity();
            }
            return self.double(p1);
        }
        // lambda = (y2 - y1) / (x2 - x1)
        let num = field::sub(p2.y, p1.y, p);
        let den = field::inv(field::sub(p2.x, p1.x, p), p);
        let lam = field::mul(num, den, p);
        self.from_lambda(p1, p2, lam)
    }

    pub fn double(&self, pt: &Point) -> Point {
        if pt.inf {
            return *pt;
        }
        let p = self.p;
        if pt.y == 0 {
            return Point::infinity();
        }
        // lambda = (3x^2 + a) / (2y)
        let x2 = field::mul(pt.x, pt.x, p);
        let three_x2 = field::mul(3, x2, p);
        let num = field::add(three_x2, self.a, p);
        let den = field::inv(field::mul(2, pt.y, p), p);
        let lam = field::mul(num, den, p);
        self.from_lambda(pt, pt, lam)
    }

    #[inline]
    fn from_lambda(&self, p1: &Point, p2: &Point, lam: u64) -> Point {
        let p = self.p;
        let lam2 = field::mul(lam, lam, p);
        let x3 = field::sub(field::sub(lam2, p1.x, p), p2.x, p);
        let y3 = field::sub(field::mul(lam, field::sub(p1.x, x3, p), p), p1.y, p);
        Point::affine(x3, y3)
    }

    /// k * P. Returns the result and the number of group operations performed
    /// (doublings + additions), so the oracle can charge `scalar_mul` fairly.
    pub fn scalar_mul(&self, k: u64, pt: &Point) -> (Point, u64) {
        let mut acc = Point::infinity();
        let mut base = *pt;
        let mut e = k;
        let mut ops: u64 = 0;
        while e > 0 {
            if e & 1 == 1 {
                acc = self.add(&acc, &base);
                ops += 1;
            }
            e >>= 1;
            if e > 0 {
                base = self.double(&base);
                ops += 1;
            }
        }
        (acc, ops)
    }
}
