//! UNTRUSTED child. Thin glue: wire stdin/stdout to the protocol, run the
//! contestant's `solver::solve`, submit the answer. All the interesting (and
//! editable) logic is in `src/solver/mod.rs`. This file is not editable.

use ecdlp_challenge::client::Client;
use ecdlp_challenge::solver;
use std::io::{stdin, stdout, BufReader, BufWriter};

fn main() {
    let reader = Box::new(BufReader::new(stdin()));
    let writer = Box::new(BufWriter::new(stdout()));
    let mut client = Client::handshake(reader, writer);
    let k = solver::solve(&mut client);
    let _ = client.submit(k); // oracle owns scoring; we just deliver the answer
}
