"""Local interactive secret setup. Does not call providers or redeem coupons."""
import getpass
import os
from pathlib import Path
p=Path(__file__).parent/'.env'
if p.exists():
    print('agent/.env already exists. Open it privately to edit; nothing was overwritten.')
    raise SystemExit(0)
provider=input('Speech: gradium, openai, or hybrid [gradium]: ').strip() or 'gradium'
if provider not in {'gradium','openai','hybrid'}:raise SystemExit('Unknown option.')
values={'SPEECH_PROVIDER':provider}
values['GENERAL_COMPUTE_API_KEY']=getpass.getpass('General Compute API key (hidden): ').strip()
if provider in {'gradium','hybrid'}:values['GRADIUM_API_KEY']=getpass.getpass('Gradium API key (hidden): ').strip()
if provider in {'openai','hybrid'}:values['OPENAI_API_KEY']=getpass.getpass('OpenAI API key (hidden): ').strip()
if any('\n' in v or '\r' in v for v in values.values()):raise SystemExit('Invalid multiline setting.')
text=(Path(__file__).parent/'.env.example').read_text()
lines=[]
for line in text.splitlines():
    key=line.split('=',1)[0]
    lines.append(key+'='+values[key] if key in values else line)
fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,'w') as f:f.write('\n'.join(lines)+'\n')
print('Private agent/.env created. No provider requests made. Keys are not verified yet.')
