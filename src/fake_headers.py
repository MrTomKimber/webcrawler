import random

fake_header_data = [
{
    "accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language":"en-GB,en-US;q=0.9,en;q=0.8",
    "cache-control":"no-cache",
    "pragma":"no-cache",
    "priority":"u=0, i",
    "sec-ch-ua":"\"Chromium\";v=\"130\", \"Google Chrome\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
    "sec-ch-ua-mobile":"?0",
    "sec-ch-ua-platform":"Linux",
    "sec-fetch-dest":"document",
    "sec-fetch-mode":"navigate",
    "sec-fetch-site":"none",
    "sec-fetch-user":"?1",
    "upgrade-insecure-requests":"1",
    "user-agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
},
{
    "accept":"*/*",
    #"accept-encoding":"gzip, deflate, br, zstd",
    "accept-language":"en-GB,en-US;q=0.9,en;q=0.8",
    "priority":"u=1, i",
    "sec-ch-ua":"\"Google Chrome\";v=\"137\", \"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"",
    "sec-ch-ua-mobile":"?0",
    "sec-ch-ua-platform":"Windows",
    "sec-fetch-dest":"empty",
    "sec-fetch-mode":"cors",
    "sec-fetch-site":"same-origin",
    "user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
} ,
{
    "accept":"*/*",
    #"accept-encoding":"gzip, deflate, br, zstd",
    "accept-language":"en-US,en;q=0.9,en-GB;q=0.8",
    "priority":"u=1, i",
    "sec-ch-ua":"\"Microsoft Edge\";v=\"137\", \"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"",
    "sec-ch-ua-mobile":"?0",
    "sec-ch-ua-platform":"Windows",
    "sec-fetch-dest":"empty",
    "sec-fetch-mode":"cors",
    "sec-fetch-site":"same-origin",
    "user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0"}
]

def fake_header():
    """Return a random header from the fake_headers_list"""
    fh = fake_header_data[random.randint(0,len(fake_header_data)-1)]
    return fh