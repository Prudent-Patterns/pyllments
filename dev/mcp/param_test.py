import param
import asyncio  # Import asyncio to run the async function

class Test(param.Parameterized):
    test_callable = param.Callable(default=None, allow_refs=True, allow_None=True)

async def test_func():
    print('test')

# Create an instance of Test and run the async function
test = Test(test_callable=test_func)
asyncio.run(test.test_callable())  # Run the async function
