#!/usr/bin/env python3
"""
Script de verificación de dependencias
Ejecuta esto ANTES de deployar para verificar que todo funciona
"""

import sys

print("🔍 Verificando dependencias...\n")

errors = []
warnings = []

# Test imports críticos
try:
    import streamlit as st
    print("✅ streamlit")
except ImportError as e:
    errors.append(f"❌ streamlit: {e}")

try:
    import langchain
    print("✅ langchain")
except ImportError as e:
    errors.append(f"❌ langchain: {e}")

try:
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    print("✅ langchain_openai")
except ImportError as e:
    errors.append(f"❌ langchain_openai: {e}")

try:
    from langchain_community.vectorstores import Chroma
    print("✅ langchain_community")
except ImportError as e:
    errors.append(f"❌ langchain_community: {e}")

try:
    import chromadb
    print("✅ chromadb")
except ImportError as e:
    errors.append(f"❌ chromadb: {e}")

try:
    from pypdf import PdfReader
    print("✅ pypdf")
except ImportError as e:
    errors.append(f"❌ pypdf: {e}")

try:
    import pandas as pd
    print("✅ pandas")
except ImportError as e:
    errors.append(f"❌ pandas: {e}")

try:
    from sentence_transformers import SentenceTransformer
    print("✅ sentence_transformers")
except ImportError as e:
    errors.append(f"❌ sentence_transformers: {e}")

try:
    import tiktoken
    print("✅ tiktoken")
except ImportError as e:
    errors.append(f"❌ tiktoken: {e}")

try:
    from dotenv import load_dotenv
    print("✅ python-dotenv")
except ImportError as e:
    errors.append(f"❌ python-dotenv: {e}")

# Verificar módulos propios
print("\n🔍 Verificando módulos propios...\n")

try:
    from ia_motor import obtener_motor
    print("✅ ia_motor.py")
except Exception as e:
    errors.append(f"❌ ia_motor.py: {e}")

try:
    from chat_procesos import ChatProcessor
    print("✅ chat_procesos.py")
except Exception as e:
    errors.append(f"❌ chat_procesos.py: {e}")

try:
    from procesar_datos import DataProcessor
    print("✅ procesar_datos.py")
except Exception as e:
    errors.append(f"❌ procesar_datos.py: {e}")

# Verificar variables de entorno
print("\n🔍 Verificando configuración...\n")

import os
if os.getenv("OPENAI_API_KEY"):
    print("✅ OPENAI_API_KEY configurada")
else:
    warnings.append("⚠️  OPENAI_API_KEY no encontrada (necesaria para funcionar)")

# Verificar carpetas
from pathlib import Path

carpetas_requeridas = [
    "Manual Solicitudes",
    "Manual Facturacion",
    "data",
    "logs"
]

for carpeta in carpetas_requeridas:
    if Path(carpeta).exists():
        print(f"✅ Carpeta '{carpeta}' existe")
    else:
        warnings.append(f"⚠️  Carpeta '{carpeta}' no existe (se creará automáticamente)")

# Resumen
print("\n" + "="*60)
print("📊 RESUMEN")
print("="*60 + "\n")

if errors:
    print("❌ ERRORES CRÍTICOS:")
    for error in errors:
        print(f"  {error}")
    print("\n⚠️  Debes resolver estos errores antes de deployar\n")
    sys.exit(1)

if warnings:
    print("⚠️  ADVERTENCIAS:")
    for warning in warnings:
        print(f"  {warning}")
    print()

if not errors and not warnings:
    print("✅ ¡Todo perfecto! Listo para deploy\n")
elif not errors:
    print("✅ Dependencias OK. Las advertencias no impiden el deploy\n")

print("🚀 Puedes ejecutar la app con: streamlit run app.py\n")
