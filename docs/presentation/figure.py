"""All 37 signed actions, exact in-window cumulative balance, source-bound lineage."""
from pathlib import Path
import json,csv,html,base64
from datetime import date
from decimal import Decimal as D
P=Path(__file__).resolve().parent;root=P.parents[1];r=json.loads((P/'ledger-check.json').read_text());rows=list(csv.DictReader((P/'award-actions.csv').open()));assert len(rows)==37;index=r['selectedIndex'];selected=rows[index];assert selected['modification_number']=='P00050';fonts=root/'app/dist/assets/fonts';sans=base64.b64encode((fonts/'dm-sans-0.woff2').read_bytes()).decode();serif=base64.b64encode((fonts/'libre-caslon-display-3.woff2').read_bytes()).decode()
def T(x,y,s,z=16,c='#153e34',family='CivicSans'):return f'<text x="{x}" y="{y}" font-family="{family}, Arial, sans-serif" font-size="{z}" fill="{c}">{html.escape(s)}</text>'
def draw(phone):
 W=375 if phone else 1280;H=1056 if phone else 724;slug='ledger-mobile'if phone else'ledger';a=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="{slug}-title {slug}-desc"><title id="{slug}-title">A reduction belongs in the ledger</title><desc id="{slug}-desc">All 37 retained actions of one NRC award contribute to an in-window cumulative commitment step plot, including the negative 1,335,317.53 dollar P00050 adjustment; the sum reconciles to 53,852,868.10 dollars, which is not cash paid or evidence of wrongdoing.</desc><style>@font-face{{font-family:CivicSans;src:url(data:font/woff2;base64,{sans})}}@font-face{{font-family:CivicSerif;src:url(data:font/woff2;base64,{serif})}}</style><rect width="100%" height="100%" fill="#f7f6ef"/>',T(24,35,'CivicLedger / FOLLOW A SIGNED ACTION',13)]
 if phone:a +=[T(24,83,'A reduction belongs',32,family='CivicSerif'),T(24,132,'in the ledger.',34,family='CivicSerif')]
 else:a +=[T(40,99,'A reduction belongs in the ledger.',50,family='CivicSerif')]
 by=172 if phone else 159;a +=[T(24 if phone else 40,by,'MODIFICATION P00050 · 25 MAY 2023',13,'#697367'),T(24 if phone else 40,by+(49 if phone else 57),'−$1,335,317.53',36 if phone else 49,'#974a39',family='CivicSerif'),T(24 if phone else 40,by+(86 if phone else 104),'Award 31310018F0052',17),T(24 if phone else 40,by+(116 if phone else 132),'TEKSYNAP CORPORATION · NRC',14,'#697367')]
 if not phone:a +=[T(754,173,'37 source actions · FY2022–FY2024',21),T(754,211,'$56,164,185.63 positive',23),T(754,244,'−$2,311,317.53 adjustments',23,'#974a39'),T(754,280,'$53,852,868.10 net commitments',23)]
 plotx=56 if phone else 88;ploty=379 if phone else 365;pw=295 if phone else 1144;ph=216 if phone else 230;lo=date.fromisoformat(rows[0]['action_date']).toordinal();hi=date.fromisoformat(rows[-1]['action_date']).toordinal();ymax=60000000
 def xy(row):return(plotx+(date.fromisoformat(row['action_date']).toordinal()-lo)/(hi-lo)*pw,ploty+ph*(1-float(D(row['cumulative_in_cohort_obligation']))/ymax))
 a.append(T(24 if phone else 40,ploty-31,'CUMULATIVE IN-WINDOW OBLIGATIONS / $ MILLIONS',10 if phone else 13,'#697367'))
 for value in[0,20,40,60]:
  yy=ploty+ph*(1-value/60);a.append(f'<line x1="{plotx}" y1="{yy}" x2="{plotx+pw}" y2="{yy}" stroke="#c7cec4"/>');a.append(T(24 if phone else 48,yy+4,str(value),12,'#697367'))
 points=[];prior=0
 for row in rows:
  x,y=xy(row);points +=[(x,ploty+ph*(1-prior/ymax)),(x,y)];prior=float(D(row['cumulative_in_cohort_obligation']))
 a.append('<polyline id="ledger-steps" points="'+' '.join(f'{x:.8f},{y:.8f}'for x,y in points)+'" fill="none" stroke="#153e34" stroke-width="2.5"/>')
 for i,row in enumerate(rows):
  x,y=xy(row);a.append(f'<circle class="action" data-index="{i}" cx="{x:.8f}" cy="{y:.8f}" r="{4 if i==index else 2}" fill="{("#974a39"if i==index else"#153e34")}"/>')
 a +=[T(plotx,ploty+ph+26,'03 Jan 2022',12,'#697367'),T(plotx+pw-(86 if phone else 78),ploty+ph+26,'14 Aug 2024',12,'#697367')]
 if phone:
  for y,s,z,c in[(668,'Every signed action stays in the sum.',17,'#153e34'),(713,'$56,164,185.63 positive',19,'#153e34'),(750,'−$2,311,317.53 adjustments',19,'#974a39'),(792,'$53,852,868.10 net',24,'#153e34'),(849,'37 actions · 1 award · 1 recipient identifier',13,'#697367'),(888,'Source: Treasury / USAspending snapshot',13,'#697367'),(917,'20261026T015420Z · NRC FY2022–FY2024',13,'#697367'),(974,'Commitments, not cash paid.',17,'#153e34'),(1012,'A selected record, not evidence of wrongdoing.',13,'#697367')]:a.append(T(24,y,s,z,c))
 else:a +=[T(40,663,'Source: Treasury / USAspending snapshot 20261026T015420Z. All 37 actions shown; steps hold between observed actions.',17,'#697367'),T(40,702,'Window begins with zero in-cohort balance. These are commitments, not cash paid, lifetime award funding or evidence of wrongdoing.',16,'#697367')]
 a.append('</svg>');return''.join(a)
for phone in[False,True]:(P/('ledger-mobile.svg'if phone else'ledger.svg')).write_text(draw(phone))
