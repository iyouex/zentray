#!/usr/bin/env python3
"""AES-GCM / MD5 跨实现对照：解密 node(webcrypto) 产出的向量，再产出向量供 node 解。

前置：先运行 node tests/frontend_core_test.mjs（写出 /tmp/text-toolbox-aes-js.json）。
依赖：python3 + cryptography（pip 包，仅自测用，插件本体零依赖）。
用法：python3 tests/cross_check.py
"""
from __future__ import annotations

import hashlib
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

JS_VEC = "/tmp/text-toolbox-aes-js.json"
PY_VEC = "/tmp/text-toolbox-aes-py.json"


def derive(password: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=iterations)
    return kdf.derive(password.encode())


def main() -> int:
    # 1) MD5：hashlib 与 JS 内联实现共享已知向量
    for text, want in [
        ("abc", "900150983cd24fb0d6963f7d28e17f72"),
        ("", "d41d8cd98f00b204e9800998ecf8427e"),
        ("中文摘要测试", "782d3b349cf3d83f0dd0ff0459a8b32d"),
    ]:
        got = hashlib.md5(text.encode()).hexdigest()
        assert got == want, (text, got)
    print("[PASS] python hashlib md5 对照向量 x3")

    # 2) 解 node 侧向量：blob = salt16 + iv12 + ct||tag16
    with open(JS_VEC, encoding="utf-8") as f:
        v = json.load(f)
    import base64
    blob = base64.b64decode(v["b64"])
    salt, iv, ct = blob[:16], blob[16:28], blob[28:]
    key = derive(v["password"], salt, v["iter"])
    pt = AESGCM(key).decrypt(iv, ct, None).decode()
    assert pt == v["plaintext"], "解密结果与明文不一致"
    print("[PASS] python cryptography 解密 node/webcrypto AES-GCM 向量（含中文+emoji）")

    # 3) 产出 python 侧向量（固定 salt/iv → 确定性），供 node --verify-py 解
    password = "跨实现-口令 python→node"
    plaintext = "AES-GCM interop：python cryptography 加密，node webcrypto 解密 ✅"
    salt = bytes(range(16))
    iv = bytes(range(12))
    ct = AESGCM(derive(password, salt, 100_000)).encrypt(
        iv, plaintext.encode(), None)
    out = base64.b64encode(salt + iv + ct).decode()
    with open(PY_VEC, "w", encoding="utf-8") as f:
        json.dump({"password": password, "plaintext": plaintext,
                   "b64": out, "iter": 100_000}, f, ensure_ascii=False)
    print(f"[PASS] python 侧向量已写出 {PY_VEC}")
    return 0


if __name__ == "__main__":
    if not os.path.exists(JS_VEC):
        raise SystemExit(f"缺少 {JS_VEC}，请先运行 node tests/frontend_core_test.mjs")
    raise SystemExit(main())
