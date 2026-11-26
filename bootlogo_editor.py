"""Editor local de splash do Atmosphère (PK31, 8 MiB)."""
from pathlib import Path
import hashlib
import os
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageOps, ImageTk

SIZE = 0x800000
START, END = 0x400000, 0x7C0000
WIDTH, HEIGHT, STRIDE = 720, 1280, 768
ROW = STRIDE * 4
VISIBLE = WIDTH * 4
SCREEN = (1280, 720)


def validate(data):
    if len(data) != SIZE:
        raise ValueError(f'Tamanho incompatível: {len(data):,} bytes. Esperado: {SIZE:,} bytes.')
    if data[:4] != b'PK31':
        raise ValueError('Assinatura PK31 ausente. Nenhum arquivo será alterado.')


def extract(data):
    validate(data)
    pixels = Image.frombytes('RGBA', (WIDTH, HEIGHT), data[START:END], 'raw', 'BGRA', ROW, 1)
    return pixels.transpose(Image.Transpose.ROTATE_270)


def prepare(image, mode='Ajustar com fundo preto', orientation='Automática'):
    image = ImageOps.exif_transpose(image).convert('RGBA')
    if orientation == 'Retrato já rotacionado' or (orientation == 'Automática' and image.size == (720, 1280)):
        image = image.transpose(Image.Transpose.ROTATE_270)
    if mode == 'Preencher (recortar)':
        image = ImageOps.fit(image, SCREEN, Image.Resampling.LANCZOS)
    elif mode == 'Esticar':
        image = image.resize(SCREEN, Image.Resampling.LANCZOS)
    else:
        image = ImageOps.contain(image, SCREEN, Image.Resampling.LANCZOS)
    out = Image.new('RGBA', SCREEN, (0, 0, 0, 255))
    out.alpha_composite(image, ((SCREEN[0]-image.width)//2, (SCREEN[1]-image.height)//2))
    return out


def patch(data, image):
    validate(data)
    if image.size != SCREEN:
        raise ValueError('A imagem preparada precisa ter 1280 × 720.')
    raw = image.convert('RGBA').transpose(Image.Transpose.ROTATE_90).tobytes('raw', 'BGRA')
    region = bytearray(END-START)
    for y in range(HEIGHT):
        region[y*ROW:y*ROW+VISIBLE] = raw[y*VISIBLE:(y+1)*VISIBLE]
    result = data[:START] + bytes(region) + data[END:]
    validate(result)
    if result[:START] != data[:START] or result[END:] != data[END:]:
        raise ValueError('Falha na verificação dos dados externos à imagem.')
    if extract(result).tobytes() != image.convert('RGBA').tobytes():
        raise ValueError('Falha na verificação da imagem gravada.')
    return result


def atomic_write(path, data):
    fd, tmp = tempfile.mkstemp(prefix='.bootlogo-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if Path(tmp).read_bytes() != data:
            raise OSError('Falha ao verificar o arquivo salvo.')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Editor:
    def __init__(self, root):
        self.root = root
        self.data = self.source = self.original = self.input_image = self.new = None
        root.title('BootLogo Studio | Atmosphère')
        root.geometry('1040x720')
        root.minsize(800, 600)
        root.configure(bg='#111827')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame', background='#111827')
        style.configure('TLabel', background='#111827', foreground='#e5e7eb', font=('Segoe UI', 10))
        style.configure('Title.TLabel', font=('Segoe UI', 23, 'bold'), foreground='#f9fafb')
        style.configure('Sub.TLabel', foreground='#a5b4c8')
        style.configure('TButton', padding=9, font=('Segoe UI', 10))
        style.configure('Accent.TButton', background='#23685e', foreground='white')
        style.map('Accent.TButton', background=[('active','#32897c'), ('disabled','#374151')])
        frame = ttk.Frame(root, padding=22)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='BootLogo Studio', style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame, text='Atmosphère / package3   •   Editor local de splash screen', style='Sub.TLabel').pack(anchor='w', pady=(0,18))
        bar = ttk.Frame(frame); bar.pack(fill='x')
        ttk.Button(bar, text='1. Abrir package3', command=self.open_package).pack(side='left', padx=(0,8))
        self.pick = ttk.Button(bar, text='2. Escolher imagem', command=self.open_image, state='disabled'); self.pick.pack(side='left', padx=(0,8))
        self.save = ttk.Button(bar, text='3. Exportar package3', style='Accent.TButton', command=self.export, state='disabled'); self.save.pack(side='left')
        self.file_label = ttk.Label(frame, text='Nenhum package3 aberto.', style='Sub.TLabel', wraplength=920); self.file_label.pack(anchor='w', pady=10)
        settings = ttk.Frame(frame); settings.pack(fill='x', pady=(0,14))
        self.mode = tk.StringVar(value='Ajustar com fundo preto')
        self.orientation = tk.StringVar(value='Automática')
        ttk.Label(settings, text='Enquadramento:').pack(side='left')
        combo = ttk.Combobox(settings, textvariable=self.mode, values=['Ajustar com fundo preto','Preencher (recortar)','Esticar'], state='readonly', width=25); combo.pack(side='left', padx=(6,16)); combo.bind('<<ComboboxSelected>>', self.refresh)
        ttk.Label(settings, text='Orientação:').pack(side='left')
        combo = ttk.Combobox(settings, textvariable=self.orientation, values=['Automática','Paisagem normal','Retrato já rotacionado'], state='readonly', width=23); combo.pack(side='left', padx=6); combo.bind('<<ComboboxSelected>>', self.refresh)
        panels = ttk.Frame(frame); panels.pack(fill='both', expand=True)
        for i in (0,1): panels.columnconfigure(i, weight=1, uniform='preview')
        panels.rowconfigure(1, weight=1)
        ttk.Label(panels, text='IMAGEM ORIGINAL').grid(row=0,column=0,sticky='w',pady=(0,6))
        ttk.Label(panels, text='NOVA IMAGEM  •  1280 × 720').grid(row=0,column=1,sticky='w',pady=(0,6),padx=(8,0))
        self.canvases = []
        for i in (0,1):
            c = tk.Canvas(panels, bg='#030712', highlightthickness=1, highlightbackground='#334155', width=400, height=250)
            c.grid(row=1,column=i,sticky='nsew',padx=(0,8) if i==0 else (8,0)); c.bind('<Configure>', self.draw)
            self.canvases.append(c)
        self.extract_btn = ttk.Button(panels,text='Extrair original (PNG)',command=lambda: self.save_png(self.original,'splash_original.png'),state='disabled'); self.extract_btn.grid(row=2,column=0,sticky='w',pady=10)
        self.preview_btn = ttk.Button(panels,text='Salvar prévia (PNG)',command=lambda: self.save_png(self.new,'splash_nova.png'),state='disabled'); self.preview_btn.grid(row=2,column=1,sticky='w',pady=10,padx=8)
        self.status = tk.StringVar(value='Abra uma cópia do package3 do seu cartão SD.')
        ttk.Label(frame, textvariable=self.status, wraplength=930).pack(anchor='w',pady=(8,3))
        ttk.Label(frame, text='O original é preservado. Apenas a splash principal é editável; outras logos não são alteradas.', style='Sub.TLabel', wraplength=930).pack(anchor='w')

    def error(self, exc): messagebox.showerror('BootLogo Studio',str(exc),parent=self.root)

    def open_package(self):
        name = filedialog.askopenfilename(title='Abrir package3',filetypes=[('Todos os arquivos','*')])
        if not name: return
        try:
            source = Path(name).resolve(); data=source.read_bytes(); original=extract(data)
            self.source,self.data,self.original=source,data,original
            self.file_label.config(text=f'{source}  |  PK31 • 8 MiB')
            self.pick.config(state='normal'); self.extract_btn.config(state='normal')
            self.status.set('Estrutura reconhecida. Escolha a nova imagem.'); self.draw()
            if self.input_image is not None: self.refresh()
        except Exception as e: self.error(e)

    def open_image(self):
        name=filedialog.askopenfilename(title='Escolher imagem',filetypes=[('Imagens','*.png *.jpg *.jpeg *.bmp *.webp *.gif'),('Todos','*')])
        if not name: return
        try:
            with Image.open(name) as im: candidate=ImageOps.exif_transpose(im).convert('RGBA')
            self.input_image=candidate; self.refresh()
        except Exception as e: self.error(e)

    def refresh(self, event=None):
        if self.input_image is None: return
        try:
            self.new=prepare(self.input_image,self.mode.get(),self.orientation.get()); self.draw()
            self.save.config(state='normal' if self.data is not None else 'disabled'); self.preview_btn.config(state='normal')
            self.status.set(f'Imagem de entrada: {self.input_image.width} × {self.input_image.height}. Prévia pronta para exportar.')
        except Exception as e: self.error(e)

    def draw(self,event=None):
        if len(self.canvases)<2: return
        for canvas,im,placeholder in zip(self.canvases,[self.original,self.new],['Abra um package3','Escolha uma imagem']):
            canvas.delete('all'); w,h=canvas.winfo_width(),canvas.winfo_height()
            if w<5 or h<5: continue
            if im is None: canvas.create_text(w//2,h//2,text=placeholder,fill='#94a3b8',font=('Segoe UI',12)); continue
            bg=Image.new('RGBA',im.size,(0,0,0,255)); bg.alpha_composite(im)
            view=ImageOps.contain(bg.convert('RGB'),(w-8,h-8),Image.Resampling.LANCZOS)
            canvas.photo=ImageTk.PhotoImage(view); canvas.create_image(w//2,h//2,image=canvas.photo)

    def save_png(self,image,name):
        if image is None: return
        target=filedialog.asksaveasfilename(initialfile=name,defaultextension='.png',filetypes=[('PNG','*.png')])
        if not target: return
        try:
            if Path(target).resolve()==self.source or (Path(target).exists() and os.path.samefile(target,self.source)): raise ValueError('Não é permitido sobrescrever o package3 original.')
            image.save(target,format='PNG'); self.status.set(f'PNG salvo: {target}')
        except Exception as e: self.error(e)

    def export(self):
        if self.data is None or self.new is None: return
        target=filedialog.asksaveasfilename(title='Salvar em uma pasta diferente da original',initialfile='package3',filetypes=[('Todos os arquivos','*')])
        if not target: return
        try:
            path=Path(target).resolve()
            if path==self.source or (path.exists() and os.path.samefile(path,self.source)): raise ValueError('Escolha outro caminho. O original não será sobrescrito.')
            result=patch(self.data,self.new); atomic_write(path,result)
            self.status.set('Exportado e verificado: 8 MiB, bytes externos à imagem intactos.')
            messagebox.showinfo('Exportação concluída',f'Arquivo: {path}\n\nImagem e dados externos verificados.\nSHA-256: {hashlib.sha256(result).hexdigest()}\n\nMantenha o backup original no computador.',parent=self.root)
        except Exception as e: self.error(e)


if __name__=='__main__':
    root=tk.Tk(); Editor(root); root.mainloop()
