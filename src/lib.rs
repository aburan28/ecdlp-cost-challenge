//! The Generic Prime-Field ECDLP Cost Challenge — shared library.
//!
//! Trust boundary:
//!   * TRUSTED  (not contestant-editable): field, curve, rng, instance, oracle,
//!     client. These define the instance, the group, and the *meter*.
//!   * UNTRUSTED (contestant-editable): `solver` (src/solver/). It may only touch
//!     the group through `client::Client`, i.e. through counted oracle queries.
//!
//! `benchmark.json` pins `editablePaths = ["src/solver"]`, so only the solver
//! module can change between submissions; the meter and verifier are fixed.

pub mod client;
pub mod curve;
pub mod field;
pub mod instance;
pub mod oracle;
pub mod rng;
pub mod solver;
