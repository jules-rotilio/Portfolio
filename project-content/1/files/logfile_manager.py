import os
from datetime import datetime
from loggers import write_warning as warning, write_info as info, file_write as write



file_path = "/home/1a017250-5dee-482c-ba52/venvs/cloudflare/output.log"
# Only writes to the log when it rotates; the DNS script logs changes and errors itself.
size_mb = os.path.getsize(file_path) / (1024 * 1024) if os.path.exists(file_path) else 0.0

if size_mb >= 2.0:
    os.remove(file_path)
    file = os.open(file_path, os.O_CREAT | os.O_RDWR)
    write(file, "")
    info(file, str(datetime.now()))
    warning(file, f"File size: {size_mb:.2f} MB")
    info(file, "Removed file")
    os.close(file)
