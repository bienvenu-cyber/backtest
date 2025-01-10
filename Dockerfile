# Utiliser une image de base Python
FROM python:3.9-slim

# Installer les dépendances système
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    curl \
    ca-certificates \
    gcc \
    g++ \
    make \
    libpq-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Installer TA-Lib 0.4.0
WORKDIR /tmp
RUN curl -L -o ta-lib-0.4.0-src.tar.gz http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar xvzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib/ && \
    ./configure --prefix=/usr && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib ta-lib-0.4.0-src.tar.gz && \
    ldconfig

# Définir le répertoire de travail
WORKDIR /app

# Copier les fichiers nécessaires dans le conteneur
COPY requirements.txt bot2.py historical_data.csv ./

# Installer les dépendances Python
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Exposer le port (si nécessaire)
EXPOSE 8002

# Définir la commande d'exécution par défaut
CMD ["python", "bot2.py"]
