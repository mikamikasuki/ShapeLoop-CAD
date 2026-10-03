"""Bundle an already built frontend for installable Python distributions."""
from pathlib import Path
import shutil
root=Path(__file__).resolve().parents[1]
source=root/"frontend/dist"
if not (source/"index.html").is_file(): raise SystemExit("Run npm ci && npm run build in frontend first")
target=root/"shapeloop/static"
if target.exists(): shutil.rmtree(target)
shutil.copytree(source,target)
licenses=root/'docs/licenses/frontend'
if licenses.exists(): shutil.copytree(licenses,target/'licenses')
notice=root/'THIRD_PARTY_NOTICES.md'
if notice.exists(): shutil.copy2(notice,target/'THIRD_PARTY_NOTICES.md')
print(f"Bundled frontend in {target}")
