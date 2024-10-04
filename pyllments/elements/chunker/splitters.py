from collections import namedtuple
from io import TextIOWrapper

from langchain_text_splitters import RecursiveCharacterTextSplitter


def base_text_splitter(
        file: TextIOWrapper, 
        chunk_size: int = 200, # TODO Change to a golden value later
        chunk_overlap: int = 20, 
        length_function = len, 
        keep_separator = False):
    # namedtuple used for efficiency
    Chunk = namedtuple('Chunk', ['text', 'start_index', 'end_index'])
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, 
        chunk_overlap=chunk_overlap, 
        add_start_index=True,
        length_function=length_function,
        keep_separator=keep_separator)
    file_text = file.decode('utf-8')
    documents = text_splitter.create_documents([file_text])
    chunk_list = []
    for doc in documents:
        text = doc.page_content
        start_index = doc.metadata['start_index']
        end_index = start_index + len(text)
        chunk_list.append(Chunk(text=text, start_index=start_index, end_index=end_index))
    return chunk_list