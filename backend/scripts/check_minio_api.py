import inspect

import minio
from minio import Minio

print("minio version:", getattr(minio, "__version__", "unknown"))
print("signature:", inspect.signature(Minio.copy_object))
print()
print((inspect.getdoc(Minio.copy_object) or "")[:900])