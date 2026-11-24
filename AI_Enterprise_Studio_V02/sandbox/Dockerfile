FROM mcr.microsoft.com/playwright/python:v1.55.0-noble
RUN python -m pip install --no-cache-dir playwright==1.55.0
WORKDIR /opt/aes
COPY browser_worker.py /opt/aes/browser_worker.py
USER 1000:1000
ENTRYPOINT ["python","-I","-B","/opt/aes/browser_worker.py"]
