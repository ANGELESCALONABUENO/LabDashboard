"""Render a private runtime copy from the anonymized source snapshot."""
import argparse,json,shutil,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',default='runtime');a=p.parse_args()
root=Path(__file__).resolve().parent;target=Path(a.output).resolve()
if target==root or target in root.parents:raise SystemExit('Choose a separate runtime folder')
values=json.loads(Path(a.config).read_text())
for key,value in values.items():
 if not re.fullmatch(r'192\.0\.2\.\d+',key) or not re.fullmatch(r'[A-Za-z0-9.-]+',value):raise SystemExit('Use documented example IP keys and a hostname/IP without URL or credentials')
target.mkdir(parents=True,exist_ok=True)
for src in list(root.glob('*.py'))+list((root/'web').glob('*')):
 if not src.is_file():continue
 dest=target/src.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True)
 if src.suffix in ('.py','.html','.js','.css','.svg'):
  text=src.read_text()
  for key in sorted(values,key=len,reverse=True):text=re.sub(re.escape(key)+r'(?!\d)',lambda m:values[key],text)
  dest.write_text(text)
 else:shutil.copy2(src,dest)
print('Runtime prepared:',target)
