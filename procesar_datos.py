# procesar_datos.py - Procesador de Datos PDF
"""
Procesa PDFs desde carpetas de manuales
Genera vectorstore para RAG con manejo seguro de concurrencia
"""

import logging
import os
import json
import time
from pathlib import Path
from typing import List, Dict, Tuple, Any
from datetime import datetime
from pypdf import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma

import config_local

logger = logging.getLogger(__name__)

class DataProcessor:
    """
    Procesa documentos PDF y los indexa en vectorstore
    Soporta carpetas de manuales
    """
    
    def __init__(self, api_key: str = None):
        """Inicializar processor"""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.vectorstore_path = "data/db/chroma_db"
        self.estadisticas_path = "data/estadisticas.json"
        
        Path(self.vectorstore_path).mkdir(parents=True, exist_ok=True)
        
        self.embeddings = None
        self.vectorstore = None
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,     # Mayor para no partir tablas/secciones
            chunk_overlap=250,
            separators=["\n\n", "\n", " ", ""]
        )
        
        logger.info("DataProcessor inicializado")
    
    def _inicializar_embeddings(self):
        """Inicializar embeddings (mismo modelo que usa ia_motor para consultar)"""
        if not self.embeddings:
            self.embeddings = config_local.crear_embeddings()
    
    def _cargar_vectorstore(self, reset: bool = False):
        """Cargar vectorstore. Si reset es True, usa un nombre de colección nuevo."""
        if not self.vectorstore or reset:
            self._inicializar_embeddings()
            
            # Si es reset, generamos un nombre único para evitar bloqueos de sqlite en la nube
            coleccion_activa = f"docs_{int(time.time())}" if reset else "documentos_procesos"
            
            self.vectorstore = Chroma(
                persist_directory=self.vectorstore_path,
                embedding_function=self.embeddings,
                collection_name=coleccion_activa
            )
    
    def procesar_carpeta(self, ruta_carpeta: str, tipo_documento: str = "general") -> Dict[str, any]:
        """Procesar todos los PDFs en una carpeta"""
        try:
            logger.info(f"🔄 Procesando carpeta: {ruta_carpeta}")
            
            if not Path(ruta_carpeta).exists():
                logger.error(f"❌ Carpeta no existe: {ruta_carpeta}")
                return {
                    'exito': False,
                    'error': f"Carpeta no encontrada: {ruta_carpeta}",
                    'archivos_procesados': 0
                }
            
            archivos_pdf = list(Path(ruta_carpeta).glob("**/*.pdf"))
            
            if not archivos_pdf:
                logger.warning(f"⚠️ No hay PDFs en {ruta_carpeta}")
                return {
                    'exito': True,
                    'archivos_procesados': 0,
                    'advertencia': 'No hay PDFs en la carpeta'
                }
            
            logger.info(f"📄 Encontrados {len(archivos_pdf)} PDFs")
            
            self._cargar_vectorstore()
            
            estadisticas = {
                'carpeta': ruta_carpeta,
                'tipo': tipo_documento,
                'archivos_totales': len(archivos_pdf),
                'archivos_procesados': 0,
                'archivos_error': 0,
                'chunks_creados': 0,
                'timestamp': datetime.now().isoformat(),
                'archivos_detalles': []
            }
            
            for archivo in archivos_pdf:
                try:
                    logger.info(f"📥 Procesando: {archivo.name}")
                    resultado = self._procesar_pdf(str(archivo), tipo_documento)
                    
                    if resultado['exito']:
                        estadisticas['archivos_procesados'] += 1
                        estadisticas['chunks_creados'] += resultado['chunks']
                        estadisticas['archivos_detalles'].append({
                            'nombre': archivo.name,
                            'chunks': resultado['chunks'],
                            'tamaño_kb': resultado['tamaño_kb'],
                            'estado': 'OK'
                        })
                        logger.info(f"✅ {archivo.name}: {resultado['chunks']} chunks")
                    else:
                        estadisticas['archivos_error'] += 1
                        estadisticas['archivos_detalles'].append({
                            'nombre': archivo.name,
                            'estado': 'ERROR',
                            'error': resultado.get('error', 'Desconocido')
                        })
                
                except Exception as e:
                    logger.error(f"❌ Error procesando {archivo.name}: {e}")
                    estadisticas['archivos_error'] += 1
            
            self._guardar_estadisticas(estadisticas)
            logger.info(f"✅ Carpeta procesada: {estadisticas['archivos_procesados']}/{len(archivos_pdf)}")
            
            return {'exito': True, **estadisticas}
        
        except Exception as e:
            logger.error(f"❌ Error procesando carpeta: {e}", exc_info=True)
            return {'exito': False, 'error': str(e), 'archivos_procesados': 0}
    
    def _procesar_pdf(self, ruta_pdf: str, tipo_documento: str = "general") -> Dict[str, any]:
        """Procesar un PDF individual"""
        try:
            with open(ruta_pdf, 'rb') as f:
                pdf_reader = PdfReader(f)
                texto_completo = ""
                
                for num_pagina, pagina in enumerate(pdf_reader.pages):
                    texto_completo += f"\n[Página {num_pagina + 1}]\n"
                    texto_completo += pagina.extract_text() or ""
            
            if not texto_completo.strip():
                return {'exito': False, 'error': 'No se pudo extraer texto del PDF'}
            
            chunks = self.splitter.split_text(texto_completo)
            
            if not chunks:
                return {'exito': False, 'error': 'No se pudieron crear chunks'}
            
            tamaño_kb = os.path.getsize(ruta_pdf) / 1024
            titulo = Path(ruta_pdf).stem.replace('_', ' ').strip()
            metadata_base = {
                'source': Path(ruta_pdf).name,
                'titulo': titulo,
                'tipo': tipo_documento,
                'ruta_completa': ruta_pdf,
                'fecha_procesamiento': datetime.now().isoformat(),
                'num_paginas': len(pdf_reader.pages),
                'tamaño_kb': round(tamaño_kb, 2)
            }
            
            # Anteponemos el TÍTULO del documento a cada chunk para que la
            # búsqueda semántica acierte el caso correcto
            # (p. ej. "cerrar un caso" -> Cerrar_un_caso.pdf)
            documentos = [
                {
                    'page_content': f"[Documento: {titulo}]\n{chunk}",
                    'metadata': {**metadata_base, 'chunk_id': i}
                }
                for i, chunk in enumerate(chunks)
            ]
            
            self.vectorstore.add_texts(
                texts=[doc['page_content'] for doc in documentos],
                metadatas=[doc['metadata'] for doc in documentos]
            )
            
            return {
                'exito': True,
                'chunks': len(chunks),
                'tamaño_kb': round(tamaño_kb, 2),
                'num_paginas': len(pdf_reader.pages)
            }
        
        except Exception as e:
            logger.error(f"❌ Error procesando PDF: {e}")
            return {'exito': False, 'error': str(e)}
    
    def _guardar_estadisticas(self, stats: Dict):
        """Guardar estadísticas en JSON"""
        try:
            Path(self.estadisticas_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.estadisticas_path, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"⚠️ No se pudieron guardar estadísticas: {e}")
    
    def obtener_estadisticas(self) -> Dict:
        """Obtener últimas estadísticas"""
        try:
            if Path(self.estadisticas_path).exists():
                with open(self.estadisticas_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except:
            pass
        return {}
    
    def limpiar_vectorstore(self) -> bool:
        """Limpiar vectorstore (Conmutación segura de colección)"""
        try:
            # 🚨 En lugar de borrar y colapsar, montamos una colección fresca
            self._cargar_vectorstore(reset=True)
            logger.info("✅ Vectorstore purgado y conmutado a colección limpia")
            
            # Borrado suave del disco (silencioso si Linux lo tiene bloqueado)
            import shutil
            try:
                if Path(self.vectorstore_path).exists():
                    shutil.rmtree(self.vectorstore_path, ignore_errors=True)
            except Exception:
                pass
                
            return True
        except Exception as e:
            logger.error(f"❌ Error crítico limpiando vectorstore: {e}")
            return False
    
    def obtener_estado_bd(self) -> Dict[str, Any]:
        """Obtener estado actual de la BD"""
        try:
            self._cargar_vectorstore()
            
            doc_count = self.vectorstore._collection.count()
            tamaño_mb = 0
            
            if Path(self.vectorstore_path).exists():
                import shutil
                tamaño_mb = shutil.disk_usage(self.vectorstore_path).used / (1024 * 1024)
            
            return {
                'documentos': doc_count,
                'tamaño_mb': round(tamaño_mb, 2),
                'ruta': self.vectorstore_path,
                'estado': 'activa'
            }
        except Exception as e:
            logger.error(f"Error obteniendo estado BD: {e}")
            return {
                'documentos': 0,
                'tamaño_mb': 0,
                'estado': 'error',
                'error': str(e)
            }
