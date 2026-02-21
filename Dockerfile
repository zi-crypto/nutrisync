# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Set default timezone for tzlocal since slim images lack tzdata
ENV TZ=Europe/Berlin

# Copy the requirements file into the container at /app
# Adjust path if requirements.txt is not at the root but inside nutrisync_adk
COPY nutrisync_adk/requirements.txt /app/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . /app

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Run app.py when the container launches
CMD ["uvicorn", "nutrisync_adk.main:app", "--host", "0.0.0.0", "--port", "8000"]
