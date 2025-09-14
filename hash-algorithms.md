Cryptographic Hash Algorithms — Concise, Accurate Overview (2025)

What a cryptographic hash function is: a deterministic function H: {0,1}* → {0,1}^n that maps arbitrary-length input to fixed-length output (digest). Security properties: **preimage resistance** (given d, infeasible to find m with H(m)=d), **second-preimage resistance** (given m1, infeasible to find m2≠m1 with H(m1)=H(m2)), **collision resistance** (infeasible to find any distinct m1,m2 with H(m1)=H(m2)). Collision resistance costs about 2^(n/2) work (birthday bound); preimage resistance about 2^n work classically.

Secure, commonly recommended algorithms (as of 2025): SHA-256 (output **256 bits**): NIST-standardized (SHA-2), no practical full-round attacks; collision ≈2^128, preimage ≈2^256; recommended for general integrity, HMAC, signatures, Merkle trees. SHA-384 / SHA-512 (outputs **384/512 bits**): larger margins; SHA-512 often faster on 64-bit platforms; SHA-512/256 gives 256-bit output with SHA-512 internal speed. SHA-3 family (Keccak; SHA3-256, SHA3-512): NIST-standardized (FIPS 202), sponge construction distinct from SHA-2, no practical full-round attacks; use for design diversity or XOF needs (SHAKE128/256 are XOFs with adjustable output length). BLAKE2 (BLAKE2b/2s): fast, secure, widely adopted (RFC 7693); good drop-in alternative to SHA-2 for performance-sensitive apps. BLAKE3: newer, very high throughput and parallelism, tree mode for chunked/parallel hashing; viewed as secure for common uses though newer than BLAKE2/SHA families.

Password hashing / KDFs: For password storage use memory-hard KDFs—**Argon2id** (winner of the PHC) is recommended with parameters tuned to your environment (memory, time, parallelism). scrypt is an alternative; PBKDF2 (with HMAC-SHA256) remains acceptable if configured with high iteration counts and unique salt but is less resistant to GPU/ASIC attacks. For general key derivation use **HKDF** (RFC 5869) built on a secure HMAC (e.g., HMAC-SHA256). For variable-length or XOF needs, use **SHAKE** (SHA-3 XOFs) or HKDF.

Obsolete or broken algorithms: **MD5** (128-bit) — practical collisions trivial; do not use for integrity, signatures, TLS, or security; **SHA-1** (160-bit) — deprecated for collision-resistant uses (practical collisions demonstrated); migrate to SHA-2/SHA-3. Avoid using raw hash outputs as cryptographic keys or authentication tokens without a proper KDF or MAC (use HKDF/HMAC).

Implementation and side-channel considerations: Prefer vetted libraries (OpenSSL, BoringSSL, libsodium, libs implementing BLAKE2/BLAKE3). Use constant-time comparisons for secret-dependent checks to avoid timing attacks. Beware of implementation bugs, padding/length-prefix pitfalls, and poor entropy sources when deriving keys.

Quantum and future considerations: Grover’s algorithm gives a quadratic speedup for preimage attacks, effectively halving the classical security bits for preimage resistance; collision resistance is affected differently. For long-term resistance consider larger digest sizes (e.g., SHA-512, SHA3-512, BLAKE2b) and algorithmic diversity.

Practical recommendations (short): Use **SHA-256** (HMAC-SHA256) for general integrity and HMACs; use **SHA-512** on 64-bit systems when extra margin is desired; prefer **BLAKE2** or **BLAKE3** when performance matters; use **SHA-3/SHAKE** when you want a different primitive family or XOF; for passwords use **Argon2id**; for KDF use **HKDF**; avoid **MD5** and **SHA-1**.

References (standards & specs): NIST FIPS 180-4 (SHA-2), NIST FIPS 202 (SHA-3), RFC 7693 (BLAKE2), Argon2 specification and PHC materials, RFC 5869 (HKDF), HMAC RFCs, published cryptanalysis (e.g., SHA-1 collision papers).


Root: Cryptographic Hash Algorithms
- SHA-2
  - SHA-256
    - Output: 256 bits
    - Strength: collision ≈ 2^128, preimage ≈ 2^256
    - Use: integrity, HMAC, signatures, blockchain
    - Notes: Widely supported, safe in 2025
  - SHA-384 / SHA-512
    - Output: 384 / 512 bits
    - Strength: higher margins; SHA-512 faster on 64-bit
    - Use: higher-security margin, 64-bit optimized
    - Note: SHA-512/256 variant = SHA-512 internal with 256-bit output
- SHA-3 (Keccak)
  - SHA3-256 / SHA3-512
    - Construction: sponge
    - Output: 256 / 512 bits
    - Use: algorithmic diversity; alternative to SHA-2
  - SHAKE128 / SHAKE256 (XOF)
    - Feature: extendable output (variable length)
    - Use: KDFs, domain separation, variable-length digests
- BLAKE family
  - BLAKE2 (BLAKE2b / BLAKE2s)
    - Output: variable (commonly 256/512)
    - Feature: very fast, secure, keyed mode available
    - Use: drop-in high-performance replacement for SHA-2
  - BLAKE3
    - Output: default 256-bit (configurable)
    - Feature: extremely fast, SIMD & parallel/tree mode
    - Use: high-throughput hashing, content-addressing
    - Note: newer but well-reviewed
- MD5
  - Output: 128 bits
  - Status: Broken
  - Issue: trivial practical collisions; do NOT use for security
- SHA-1
  - Output: 160 bits
  - Status: Deprecated for collision resistance
  - Issue: practical collisions exist; migrate to SHA-2/SHA-3
- Password hashing / KDFs
  - Argon2 (Argon2id)
    - Feature: memory-hard, tunable (memory, time, parallelism)
    - Use: password storage (recommended)
  - scrypt
    - Feature: memory-hard, CPU+memory cost
    - Use: password hashing alternative
  - PBKDF2 (HMAC-SHA256)
    - Feature: iteration-based, widely supported
    - Use: acceptable if properly configured; less ASIC-resistant
  - HKDF
    - Feature: HMAC-based KDF, standardized
    - Use: key derivation from shared secrets
- Security & implementation notes
  - Avoid: MD5, SHA-1 for collision-sensitive uses
  - Use HMAC for message authentication (e.g., HMAC-SHA256)
  - Prefer vetted libraries (OpenSSL, libsodium, BLAKE libs)
  - Side-channels: use constant-time primitives for secrets
  - Quantum note: Grover reduces preimage security roughly by half => consider larger digests for extreme long-term security
