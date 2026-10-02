"""Source-only anchor-catalogue.v1 and mode-a route, detached offline only.

Heading recognition and label eligibility preserve the closed study grammar.
No frozen corpus hashes, fixtures, mode-b value extraction or provider access.
Catalogue recognition does not establish semantic belonging.
"""
from __future__ import annotations
import collections
import hashlib
import json
import re

VERSION = 'anchor-id-auditor.v1'
CATALOG_VERSION = 'anchor-catalogue.v1'
H = r'[ \t\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]'
EOL = r'(?:\r\n|\r(?!\n)|(?<!\r)\n)'
CODE = r'(?-i:(?:[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]|[AEIOUaeiou]\u0301|[Uu]\u0308|[Nn]\u0303){1,4}[0-9]{1,4})'
CONTENT = rf'Contenidos?(?:{H}+curricular(?:es)?)?'
PDA = rf'(?:(?:{CODE}{H}+)?PDA{H}*[0-9]+|PDAs?|Procesos?{H}+de{H}+desarrollo{H}+de{H}+aprendizajes?(?:{H}*\(PDAs?\))?)'
TYPED = re.compile(rf'(?:{CONTENT}|{PDA}){H}*:', re.I)
COMBINED = re.compile(rf'Contenidos?{H}*(?:/|y){H}*PDAs?{H}*:', re.I)
ANY_TYPED = re.compile(rf'(?<![\w\u0300-\u036f])(?:{CONTENT}|{PDA}){H}*:', re.I)
DAY = r'Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes'
SESSION_BASE = rf'(?:(?:{DAY}){H}*[-–—]?{H}*)?SESI[OÓ]\u0301?N{H}+(?P<number>0*[1-9][0-9]*)'
SESSION_SIMPLE = re.compile(rf'{SESSION_BASE}(?:{H}*[:.]{H}*(?P<title>[^\r\n]*))?{H}*', re.I)
SESSION_DATED = re.compile(rf'{SESSION_BASE}{H}+Fecha{H}*:{H}*(?:(?:{DAY}){H}+)?(?:0?[1-9]|[12][0-9]|3[01])(?={H}|[/.-]|$)[^\r\n]*', re.I)
SESSION_PARTIAL = re.compile(rf'{SESSION_BASE}{H}+Fecha{H}*:{H}*(?:{DAY})(?={H}*(?:Tema\b|Tiempo\b|Organizaci[oó]n\b|$))[^\r\n]*', re.I)
SESSION_CUE = re.compile(rf'^(?:{SESSION_BASE}|SESI[OÓ]\u0301?N\b)', re.I)
MOMENT = re.compile(rf'(?im)^{H}*(?:Inicio|Desarrollo|Cierre){H}*(?::|$)')
CUT_LINE = re.compile(rf'(?im)^{H}*(?:SESI[OÓ]\u0301?N{H}*[0-9]+\b|(?:Nombre{H}+del{H}+)?Proyecto\b|DATOS{H}+GENERALES\b)')
META = re.compile(rf'(?im)^{H}*(Campo|Contenidos/PDA|Tiempo|Organizaci[oó]n){H}*:')
PROJECT_LABEL = re.compile(rf'(?:(?:Nombre{H}+del{H}+)?Proyecto(?:{H}+(?:integrador|de{H}+diagn[oó]stico))?|P\.{H}*Integrador){H}*:', re.I)
PROJECT_REFERENCE = re.compile(rf'Proyectos?(?:{H}+(?:de{H}+Aula|Escolar(?:es)?|Comunitario(?:s)?|del{H}+Libro(?:{H}+de{H}+Texto)?)){H}*:', re.I)
EXAMPLE = re.compile(r'^(?:[-*•]\s*)?(?:Ejemplos?|Por\s+ejemplo|Citas?|Texto\s+citado|Referencias?|Menci[oó]n|(?:Se\s+)?(?:menciona|cita|ejemplifica)|Modelo|Propuesta|Sugerencia|No\s+adoptad[oa])\b',re.I)
NONAFFIRMATIVE = re.compile(r'^(?:[-*•]\s*)?(?:No\b|Nunca\b|Sin\s+(?:PDA|contenidos?|definir|especificar)\b|Ning[uú]n[oa]?\b|N/?A\b|Si\s|En\s+caso\s+de\b|Condicionad[oa]\b|Sujeto\s+a\b|De\s+ser\s+posible\b|(?:Puede|Podr[ií]a)\s+(?:trabajarse|abordarse|incluirse)\b|Se\s+(?:sugiere|propone|recomienda|omite)\b|Sugerid[oa]s?\b|Sugerencia\b|Propuest[oa]s?\b|Opcional\b|Tentativ[oa]\b|Pendiente\b|Por\s+definir\b|Posible\b|Ejemplos?\b|Por\s+ejemplo\b)', re.I)
INLINE_MOMENT = re.compile(r'\b(?:Inicio|Desarrollo|Cierre)\s*:',re.I)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def canonical(value) -> bytes:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def document_hash(pages) -> str:
    # Existing source binding is canonical list, retaining list order, not file/PDF hash.
    return sha(json.dumps(list(pages),ensure_ascii=False,separators=(',',':')).encode())

def span(page_number, text, start, end):
    return {'page_number':page_number,'start':start,'end':end,'excerpt':text[start:end]}

def lines(text):
    return [(m.start(),m.end(),m.group().rstrip('\r\n')) for m in re.finditer(r'[^\r\n]*(?:\r\n|\n|\r|$)',text) if m.group()]

def quote_open(text):
    stack=[]; pairs={'"':'"','«':'»','“':'”',"'":"'",'‘':'’'}
    for c in text:
        if stack and c==stack[-1]:stack.pop()
        elif c in pairs:stack.append(pairs[c])
    return bool(stack)

def example_context(page,start):
    # Explicit example/citation block persists to blank physical paragraph boundary.
    breaks=list(re.finditer(rf'{EOL}{H}*{EOL}',page[:start]));begin=breaks[-1].end() if breaks else 0
    for _,_,line in lines(page[max(0,begin):start]):
        if EXAMPLE.match(line.strip()) or NONAFFIRMATIVE.match(line.strip()) or line.lstrip().startswith('>'):return True
    return False

def literal_ref(ref,pages,source):
    if not isinstance(ref,dict) or ref.get('document_sha256')!=source:return False
    n=ref.get('page_number');r=ref.get('region',{})
    if not isinstance(r,dict):return False
    a=r.get('start');b=r.get('end')
    return (type(n)is int and 1<=n<=len(pages) and r.get('kind')=='text_offsets' and type(a)is int and type(b)is int and 0<=a<b<=len(pages[n-1]) and pages[n-1][a:b]==ref.get('excerpt'))

def simple_span(ref):
    return {'page_number':ref['page_number'],'start':ref['region']['start'],'end':ref['region']['end'],'excerpt':ref['excerpt']}

def label_kind(excerpt):
    if not isinstance(excerpt,str):return None
    if re.fullmatch(rf'{CONTENT}{H}*:',excerpt,re.I):return 'contenido'
    if re.fullmatch(rf'{PDA}{H}*:',excerpt,re.I):return 'pda'
    return None

def label_geometry(page,s,allow_container=False):
    a,b=s['start'],s['end']; literal=page[a:b]
    if not TYPED.fullmatch(literal):return 'not_complete_typed_colon_label'
    line_start=max(page.rfind('\n',0,a),page.rfind('\r',0,a))+1
    ends=[x for x in (page.find('\n',b),page.find('\r',b)) if x>=0];line_end=min(ends) if ends else len(page)
    prefix=page[line_start:a];line=page[line_start:line_end]
    if quote_open(page[:a]) or literal.startswith(('"','“','«')):return 'quoted_label'
    if example_context(page,line_start):return 'example_context'
    if '|' in line or '\x1f' in line:return 'mixed_row'
    if not re.fullmatch(rf'{H}*(?:-{H}*)?',prefix):
        if not (allow_container and re.fullmatch(rf'{H}*'+COMBINED.pattern+rf'{H}*',prefix,re.I)):
            return 'not_label_position'
    tail=page[b:line_end]
    if '\t' in tail.strip():return 'mixed_row'
    if ANY_TYPED.search(tail) or INLINE_MOMENT.search(tail):return 'mixed_row_or_inline_moment'
    return None

def source_documents(source):
    if not isinstance(source,dict) or not isinstance(source.get('documents'),list) or not source['documents']:raise ValueError('invalid source documents')
    seen=set()
    for doc in source['documents']:
        if not isinstance(doc,dict) or not isinstance(doc.get('id'),str) or not doc['id'].strip() or doc['id'] in seen:raise ValueError('invalid or duplicate document identity')
        pages=doc.get('pages')
        if not isinstance(pages,list) or not pages or len(pages)>6 or not all(isinstance(p,str) for p in pages):raise ValueError('invalid source page window')
        seen.add(doc['id'])
    return source['documents']

def catalogue_from_sources(source,*,source_windows_sha256=None):
    entries=[];rejections=[];page_ledger=[]
    for doc in source_documents(source):
        did=doc['id'];pages=doc['pages'];dsha=document_hash(pages)
        for n,page in enumerate(pages,1):
            before=len(entries);reject_before=len(rejections)
            for a,e,line in lines(page):
                raw=line.strip();start=a+len(line)-len(line.lstrip());end=a+len(line.rstrip())
                if not raw:continue
                kind=None;eligibility='selectable';support=[n];reason='literal_heading';m=None
                if SESSION_CUE.match(raw):
                    if not re.search(r'SESI[OÓ]\u0301?N'+H+r'*[0-9]+\b',raw,re.I):
                        rejections.append({'document_id':did,'page_number':n,'start':start,'end':end,'excerpt':page[start:end],'reason':'session_mention_without_number'});continue
                    kind='session';simple=SESSION_SIMPLE.fullmatch(raw);dated=SESSION_DATED.fullmatch(raw);partial=SESSION_PARTIAL.fullmatch(raw)
                    m=simple or dated or partial
                    cuts=[x.start() for x in CUT_LINE.finditer(page,e)];stop=min(cuts) if cuts else len(page);block=page[e:stop]
                    body=bool(MOMENT.search(block))
                    metadata={x[1].casefold() for x in META.finditer(block)}
                    section=bool(re.search(r'(?im)^\s*Descripci[oó]n de actividades\s*:',block))
                    if partial:body=body and len(metadata)>=2 and section
                    if dated and not body and stop==len(page) and n<len(pages):
                        following=pages[n];nextcuts=[x.start() for x in CUT_LINE.finditer(following)];prefix=following[:min(nextcuts)] if nextcuts else following
                        nextmoment=MOMENT.search(prefix)
                        if nextmoment:
                            first=prefix[:nextmoment.start()]
                            if (len(metadata)>=2 and re.search(r'(?im)^\s*Descripci[oó]n de actividades\s*:',first)) or (re.search(r'\bTiempo\s*:',raw,re.I) and re.search(r'(?im)^\s*Fase\s*:',first) and re.search(r'(?im)^\s*Prop[oó]sito\s*:',first)):
                                body=True;support.append(n+1)
                    if not m or (not simple and not body):reason='unknown_or_uncorroborated_session';eligibility='ambiguous'
                    if simple and simple.groupdict().get('title') and (EXAMPLE.match(simple['title']) or NONAFFIRMATIVE.match(simple['title']) or '|' in simple['title'] or '\x1f' in simple['title'] or '\t' in simple['title'].strip() or ANY_TYPED.search(simple['title']) or INLINE_MOMENT.search(simple['title'])):
                        reason='mixed_or_example_session';eligibility='ambiguous'
                    # Mixed-row negatives apply equally to dated/partial forms;
                    # ordinary Fecha/Tiempo metadata colons remain permitted.
                    if '|' in raw or '\x1f' in raw or '\t' in raw or ANY_TYPED.search(raw) or INLINE_MOMENT.search(raw):
                        reason='mixed_or_example_session';eligibility='ambiguous'
                elif PROJECT_LABEL.match(raw) or PROJECT_REFERENCE.match(raw) or re.fullmatch(r'PROYECTO\s+INTEGRADOR',raw,re.I):
                    kind='project';m=PROJECT_LABEL.match(raw) or PROJECT_REFERENCE.match(raw)
                    if m and PROJECT_REFERENCE.match(raw):eligibility='reference_only';reason='explicit_reference_project'
                    if not m:
                        eligibility='ambiguous';reason='untitled_project_heading'
                    else:
                        value=raw[m.end():].strip()
                        # An explicit quoted title is complete at its matching closer;
                        # otherwise only a nonempty single physical line without labels.
                        if not value:
                            suffix=page[e:];lead=len(suffix)-len(suffix.lstrip(' \t\r\n'));qstart=e+lead
                            if qstart<len(page) and page[qstart] in '“«"':
                                close={'“':'”','«':'»','"':'"'}[page[qstart]];qend=page.find(close,qstart+1)
                                if qend>=0:
                                    # Retain the rest of the physical closing line;
                                    # stopping at the quote could hide a mixed row.
                                    ends=[x for x in (page.find('\n',qend),page.find('\r',qend)) if x>=0]
                                    line_end=min(ends) if ends else len(page)
                                    end=qstart+len(page[qstart:line_end].rstrip())
                                    value=page[qstart:end]
                        closed_title=True
                        if value and value[0] in ('“','«','"',"'",'‘'):
                            closer={'“':'”','«':'»','"':'"',"'":"'",'‘':'’'}[value[0]];close_at=value.find(closer,1)
                            closed_title=close_at>1 and not value[close_at+1:].strip(' .!?')
                        if not value or ':' in value or '|' in value or '\x1f' in value or '\t' in value.strip() or NONAFFIRMATIVE.match(value) or EXAMPLE.match(value) or not closed_title:
                            eligibility='ambiguous' if eligibility!='reference_only' else eligibility;reason='missing_or_ambiguous_project_title'
                elif re.match(r'Proyecto\s+del\s+Libro\s*$',raw,re.I):
                    # Explicit wrapped reference heading only; never a planning unit.
                    following=page[e:];mref=re.match(r'[ \t]*de\s+Texto\s*:',following,re.I)
                    if mref:kind='project';eligibility='reference_only';reason='wrapped_book_reference';end=e+mref.end()
                if kind is None:continue
                if quote_open(page[:start]) or example_context(page,start):
                    rejections.append({'document_id':did,'page_number':n,'start':start,'end':end,'excerpt':page[start:end],'reason':'quoted_or_example_heading'});continue
                excerpt=page[start:end];binding={'document_id':did,'document_sha256':dsha,'page_number':n,'start':start,'end':end,'kind':kind,'excerpt_sha256':sha(excerpt.encode())}
                anchor_id='anchor:'+sha(canonical(binding))
                entries.append({**binding,'anchor_id':anchor_id,'excerpt':excerpt,'eligibility':eligibility,'support_pages':support,'repeated_literal':False,'recognition_reason':reason})
            page_ledger.append({'document_id':did,'page_number':n,'page_sha256':sha(page.encode()),'characters':len(page),'anchor_count':len(entries)-before,'rejected_heading_count':len(rejections)-reject_before})
    counts=collections.Counter((e['document_id'],e['kind'],e['excerpt']) for e in entries)
    for e in entries:e['repeated_literal']=counts[e['document_id'],e['kind'],e['excerpt']]>1
    return {'catalog_version':CATALOG_VERSION,'source_windows_sha256':source_windows_sha256 or sha(canonical(source)),'entries':entries,'rejected_headings':rejections,'page_ledger':page_ledger,'scope_semantics_approved':False}

def route_record(doc,record):
    if not isinstance(record,dict) or not isinstance(record.get('id'),str) or not record['id'].strip():raise ValueError('invalid record identity')
    pages=doc['pages'];source=document_hash(pages);ev=record.get('evidence',[])
    if not isinstance(ev,list) or not all(isinstance(e,dict) for e in ev):raise ValueError('invalid prior evidence')
    labels=[e for e in ev if e.get('role')=='label'];values=[e for e in ev if e.get('role')=='value']
    row={'document_id':doc['id'],'document_sha256':source,'record_id':record['id'],'prior_reason':record.get('reason'),'prior_decision':record.get('decision'),'prior_unit':record.get('unit'),'kind':record.get('kind'),'eligible':False,'mode':None,'route_reason':None,'label_span':None,'immutable_value_span':None}
    def done(reason,mode=None):
        row.update(route_reason=reason,eligible=mode is not None,mode=mode);return row
    if len(labels)!=1:return done('label_evidence_count')
    label=labels[0]
    if not literal_ref(label,pages,source):return done('invalid_literal_label_binding')
    ls=simple_span(label);row['label_span']=ls;page=pages[ls['page_number']-1]
    if record.get('decision')!='abstained':return done('prior_not_abstained')
    if record.get('kind') not in ('contenido','pda'):return done('not_single_typed_kind')
    if label_kind(ls['excerpt'])!=record.get('kind'):return done('label_kind_mismatch')
    if record.get('unit') is not None:return done('prior_unit_already_set')
    if record.get('reason')=='unresolved_scope':
        if len(values)!=1 or not literal_ref(values[0],pages,source):return done('invalid_or_missing_prior_value')
        vs=simple_span(values[0]);row['immutable_value_span']=vs
        if vs['page_number']!=ls['page_number'] or vs['start']<ls['end'] or page[ls['end']:vs['start']].strip():return done('invalid_prior_label_value_relation')
        error=label_geometry(page,ls,True)
        if error:return done(error)
        if NONAFFIRMATIVE.match(vs['excerpt'].lstrip()) or EXAMPLE.match(vs['excerpt'].lstrip()):return done('nonaffirmative_prior_value')
        if vs['excerpt'].lstrip().startswith(('"',"'",'“','‘','«','>')):return done('quoted_prior_value')
        return done('literal_prior_value_unresolved_scope','a')
    return done('literal_extraction_outside_scope_audit')
