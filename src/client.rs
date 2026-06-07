//! TRUSTED glue the solver talks through — the *only* way the contestant's code
//! can touch the group. Every `add`/`neg`/`scalar_mul` is a counted oracle query.
//! Tokens are opaque 16-byte values; the solver compares them for equality but
//! learns nothing about the underlying point. Binary protocol (see `oracle.rs`).
//!
//! Not contestant-editable (lives outside `src/solver/`).

use std::io::{Read, Write};

pub type Tok = [u8; 16];

pub struct Client {
    reader: Box<dyn Read + Send>,
    writer: Box<dyn Write + Send>,
    pub n: u64,        // prime group order (public)
    pub bits: u32,
    pub tok_p: Tok,    // generator P
    pub tok_q: Tok,    // target Q = k*P
    pub tok_o: Tok,    // identity O
}

impl Client {
    /// Read the 60-byte handshake and construct the client.
    pub fn handshake(mut reader: Box<dyn Read + Send>, writer: Box<dyn Write + Send>) -> Self {
        let mut hdr = [0u8; 60];
        reader.read_exact(&mut hdr).expect("failed to read handshake");
        let n = u64::from_le_bytes(hdr[0..8].try_into().unwrap());
        let bits = u32::from_le_bytes(hdr[8..12].try_into().unwrap());
        let mut tok_p = [0u8; 16];
        let mut tok_q = [0u8; 16];
        let mut tok_o = [0u8; 16];
        tok_p.copy_from_slice(&hdr[12..28]);
        tok_q.copy_from_slice(&hdr[28..44]);
        tok_o.copy_from_slice(&hdr[44..60]);
        Client {
            reader,
            writer,
            n,
            bits,
            tok_p,
            tok_q,
            tok_o,
        }
    }

    fn read_tok(&mut self) -> Tok {
        let mut t = [0u8; 16];
        self.reader.read_exact(&mut t).expect("read token");
        t
    }

    /// Group addition. One counted group operation.
    pub fn add(&mut self, a: &Tok, b: &Tok) -> Tok {
        let mut msg = [0u8; 33];
        msg[0] = 0x01;
        msg[1..17].copy_from_slice(a);
        msg[17..33].copy_from_slice(b);
        self.writer.write_all(&msg).unwrap();
        self.writer.flush().unwrap();
        self.read_tok()
    }

    /// Batched addition: `pairs.len()` independent adds in one round trip. The
    /// honest way to scale rho — step many parallel walks per pipe trip. Charged
    /// one group op per pair.
    pub fn add_batch(&mut self, pairs: &[(Tok, Tok)]) -> Vec<Tok> {
        let count = pairs.len() as u32;
        let mut msg = Vec::with_capacity(5 + pairs.len() * 32);
        msg.push(0x06);
        msg.extend_from_slice(&count.to_le_bytes());
        for (a, b) in pairs {
            msg.extend_from_slice(a);
            msg.extend_from_slice(b);
        }
        self.writer.write_all(&msg).unwrap();
        self.writer.flush().unwrap();
        let mut buf = vec![0u8; pairs.len() * 16];
        self.reader.read_exact(&mut buf).expect("read batch");
        buf.chunks_exact(16)
            .map(|c| {
                let mut t = [0u8; 16];
                t.copy_from_slice(c);
                t
            })
            .collect()
    }

    /// Negation. FREE (−P = (x, −y) on the curve).
    pub fn neg(&mut self, a: &Tok) -> Tok {
        let mut msg = [0u8; 17];
        msg[0] = 0x02;
        msg[1..17].copy_from_slice(a);
        self.writer.write_all(&msg).unwrap();
        self.writer.flush().unwrap();
        self.read_tok()
    }

    /// Batched negation, FREE: one round trip for many points. The negation-map
    /// solver uses this to canonicalize all its parallel walks at once.
    pub fn neg_batch(&mut self, toks: &[Tok]) -> Vec<Tok> {
        let count = toks.len() as u32;
        let mut msg = Vec::with_capacity(5 + toks.len() * 16);
        msg.push(0x07);
        msg.extend_from_slice(&count.to_le_bytes());
        for t in toks {
            msg.extend_from_slice(t);
        }
        self.writer.write_all(&msg).unwrap();
        self.writer.flush().unwrap();
        let mut buf = vec![0u8; toks.len() * 16];
        self.reader.read_exact(&mut buf).expect("read neg_batch");
        buf.chunks_exact(16)
            .map(|c| {
                let mut t = [0u8; 16];
                t.copy_from_slice(c);
                t
            })
            .collect()
    }

    /// Scalar multiplication c·X. Charged the doublings+additions of double-and-add.
    pub fn scalar_mul(&mut self, a: &Tok, c: u128) -> Tok {
        let mut msg = [0u8; 33];
        msg[0] = 0x03;
        msg[1..17].copy_from_slice(a);
        msg[17..33].copy_from_slice(&c.to_le_bytes());
        self.writer.write_all(&msg).unwrap();
        self.writer.flush().unwrap();
        self.read_tok()
    }

    /// Identity test (free). Equality of two points is just `a == b` on tokens.
    pub fn is_identity(&mut self, a: &Tok) -> bool {
        let mut msg = [0u8; 17];
        msg[0] = 0x04;
        msg[1..17].copy_from_slice(a);
        self.writer.write_all(&msg).unwrap();
        self.writer.flush().unwrap();
        let mut r = [0u8; 1];
        self.reader.read_exact(&mut r).expect("read isid");
        r[0] == 1
    }

    /// Terminal: submit the recovered discrete log. Returns `(solved, group_ops)`.
    pub fn submit(&mut self, k: u128) -> (bool, u64) {
        let mut msg = [0u8; 17];
        msg[0] = 0x05;
        msg[1..17].copy_from_slice(&k.to_le_bytes());
        self.writer.write_all(&msg).unwrap();
        self.writer.flush().unwrap();
        let mut r = [0u8; 9];
        self.reader.read_exact(&mut r).expect("read submit");
        let solved = r[0] == 1;
        let count = u64::from_le_bytes(r[1..9].try_into().unwrap());
        (solved, count)
    }
}
