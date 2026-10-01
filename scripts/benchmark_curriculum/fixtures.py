"""Small deterministic hand-authored PDFs, no source corpus or product scanner."""
from pathlib import Path
from scripts.benchmark_curriculum.common import ROOT, write_json, sha_file, C01_SHA, C01_RELATIVE

def pdf_bytes(pages):
    objects=[]
    def add(data):
        objects.append(data); return len(objects)
    add(b'<< /Type /Catalog /Pages 2 0 R >>')
    add(b'')
    font=add(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>')
    ids=[]
    for lines in pages:
        commands=[b'BT /F1 10 Tf 12 TL 36 760 Td']
        for i,line in enumerate(lines):
            data=line.encode('cp1252').replace(b'\\',b'\\\\').replace(b'(',b'\\(').replace(b')',b'\\)')
            commands.append((b'T* ' if i else b'')+b'('+data+b') Tj')
        commands.append(b'ET')
        stream=b'\n'.join(commands)
        stream_id=add(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream')
        ids.append(add(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font} 0 R >> >> /Contents {stream_id} 0 R >>'.encode()))
    objects[1]=f'<< /Type /Pages /Count {len(ids)} /Kids ['.encode()+b' '.join(f'{i} 0 R'.encode() for i in ids)+b'] >>'
    result=b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'; offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(result)); result+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref=len(result); result+=f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
    result+=b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    result+=f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    return result

def build(runtime, include_c01=False):
    destination=runtime.private_path("fixtures")
    if destination.exists():
        raise ValueError("Refusing to overwrite fixtures; use a fresh private workdir")
    destination.mkdir(parents=True)
    pages=[['Proyecto: Agua del barrio','Propósito: Observar el uso del agua.','Campos formativos: Lenguajes',
            'SESIÓN 1: Observamos','Inicio: Leemos la pregunta.','Desarrollo: Anotamos ejemplos.','Cierre: Compartimos.'],
           ['Proyecto: Cuidado del parque','Finalidad: Describir el parque.','SESIÓN 1: Caminamos',
            'Inicio: Dibujamos el camino.','Desarrollo: Contamos los árboles.','Cierre: Presentamos.']]
    fixtures={'S01_repeated_projects':pages,'S02_blank_pages':[[],[],[]],
              'S03_thirty_pages':[pages[i%2]+[f'Observación sintética {i+1}: '+('palabra '*18) for _ in range(30)] for i in range(30)]}
    rows=[]
    for name,content in fixtures.items():
        path=destination/f'{name}.pdf'
        path.write_bytes(pdf_bytes(content))
        rows.append({'document_id':name,'family_id':name,'split':'X','path':str(path),'file_sha256':sha_file(path),
                     'bytes':path.stat().st_size,'page_count':len(content),'synthetic':True})
    if include_c01:
        c01=runtime.snapshots/'B3'/C01_RELATIVE
        if sha_file(c01)!=C01_SHA: raise ValueError('C01 does not match protocol')
        # Page count independently determined during fixtures, never from product output.
        from pypdf import PdfReader
        rows.insert(0,{'document_id':'C01','family_id':'C01_exposed','split':'R','path':str(c01),
                       'file_sha256':C01_SHA,'bytes':c01.stat().st_size,'page_count':len(PdfReader(c01).pages),'synthetic':False})
    write_json(destination/'manifest.json',rows)
    return rows
