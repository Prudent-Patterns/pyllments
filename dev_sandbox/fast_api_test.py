from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI()

class Item(BaseModel):
    name: str
    description: str = None
    price: float
    tax: float = None

@app.get("/")
async def root():
    return {"message": "Welcome to the FastAPI test server!"}

@app.post("/items/")
async def create_item(item: Item):
    return item

@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}

def run_server():
    print("Starting the FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
print('script works outside of the condish')
if __name__ == "__main__":
    print("Script is being run directly")
    run_server()
else:
    print("Script is being imported as a module")

# To run this script:
# 1. Install required packages: pip install fastapi uvicorn
# 2. Run the script: python fast_api_test.py
# 3. Access the API documentation at http://[YOUR_IP]:8000/docs
