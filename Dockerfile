FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# فتح المنفذ الخاص بـ Hugging Face
EXPOSE 7860
CMD ["python", "main.py"]