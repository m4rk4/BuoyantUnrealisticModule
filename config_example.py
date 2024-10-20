server = 'http://localhost:8080'
country = 'US'
local_tz = 'US/Eastern'
locale = 'en-us'

default_headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "sec-ch-ua": "\"Not_A Brand\";v=\"99\", \"Microsoft Edge\";v=\"109\", \"Chromium\";v=\"109\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36 Edg/109.0.1518.55"
}

# Local http proxy
# use https://github.com/ViRb3/wgcf to generate a Wireguard config for Cloudflare Warp
# use https://github.com/pufferffish/wireproxy to make a local http proxy through CF Warp
# Sending through CF seems to help with accessing some sites
http_proxy = "http://127.0.0.1:25345"
proxies = {
    "https": http_proxy
}

# path to the local pem file
verify_path = "C:\\Users\\windows.login\\AppData\\Roaming\\pip\\mcafee_uce.pem"

# lat, lon coordinates for default location
location = ["38.897957", "-77.036560"]

# impersonate target for curl_cffi
impersonate = "chrome110"

# For Twitter api - doesn't work after Twitter changes https://github.com/zedeus/nitter/issues/983
# generate with twitter_api.get_guest_account()
twitter_oauth_token = ''
twitter_oauth_token_secret = ''

# searXNG instance from https://searx.space/
searxng_host = 'https://searx.tiekoetter.com'
