"""Bound both wire and decoded bytes for authenticated JSON proxy reads."""
import zlib

def read_body(response, limit):
    headers = getattr(response, "headers", {})
    encoding = headers.get("Content-Encoding", "identity").strip().lower()
    if encoding not in ("identity", "gzip"):
        raise ValueError("Unsupported upstream encoding")
    length = headers.get("Content-Length")
    if length is not None and (int(length) < 0 or int(length) > limit):
        raise ValueError("Upstream response exceeds its size limit")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
    result = bytearray()
    received = 0
    while True:
        chunk = response.read(min(65536, limit + 1 - received))
        if not chunk:
            break
        received += len(chunk)
        if received > limit:
            raise ValueError("Upstream response exceeds its size limit")
        try:
            decoded = decoder.decompress(chunk, limit + 1 - len(result)) if decoder else chunk
        except zlib.error as exc:
            raise ValueError("Malformed upstream gzip") from exc
        result.extend(decoded)
        if len(result) > limit or (decoder and (decoder.unconsumed_tail or decoder.unused_data)):
            raise ValueError("Upstream decoded response exceeds its size limit or has trailing data")
    if decoder and not decoder.eof:
        raise ValueError("Truncated upstream gzip")
    return bytes(result)
