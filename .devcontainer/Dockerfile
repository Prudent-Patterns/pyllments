FROM --platform=linux/amd64 debian:bookworm-slim as main

COPY environment.yml /

# Update and upgrade system packages
RUN apt-get -y update && \
    apt-get -y upgrade && \
    apt-get clean

# Install system dependencies
RUN apt-get -y install wget git-all ffmpeg build-essential libopengl0 libsm6 libegl1

# Set up Miniconda
RUN mkdir -p ~/miniconda3 && \
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3/miniconda.sh && \
    bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3 && \
    rm -rf ~/miniconda3/miniconda.sh

# Configure Conda
RUN ~/miniconda3/bin/conda update conda && \
    ~/miniconda3/bin/conda init bash && \
    echo "conda activate pyllments" >> ~/.bashrc

# Create Conda environment from yml file
RUN ~/miniconda3/bin/conda env update --file /environment.yml

ENV PATH=$PATH:~/miniconda3/bin

CMD ["/bin/bash"]
