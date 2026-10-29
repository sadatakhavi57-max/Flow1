"""Dev-only: PHC argon2id hash with the contract's pinned params (t=3, m=65536 KiB, p=4, len 32, salt 16)."""
import base64, os, sys
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
def b64(b): return base64.b64encode(b).rstrip(b"=").decode()
def make(pw, salt=None):
    salt = salt or os.urandom(16)
    k = Argon2id(salt=salt, length=32, iterations=3, lanes=4, memory_cost=65536).derive(pw.encode())
    return f"$argon2id$v=19$m=65536,t=3,p=4${b64(salt)}${b64(k)}"
def verify(pw, phc):
    _,alg,v,params,s,h = phc.split("$")
    p = dict(x.split("=") for x in params.split(","))
    pad=lambda x: base64.b64decode(x+"="*(-len(x)%4))
    k = Argon2id(salt=pad(s), length=len(pad(h)), iterations=int(p["t"]), lanes=int(p["p"]), memory_cost=int(p["m"])).derive(pw.encode())
    return k == pad(h)
if __name__=="__main__":
    h = make(sys.argv[1]); assert verify(sys.argv[1], h) and not verify(sys.argv[1]+"x", h); print(h)
