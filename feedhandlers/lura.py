import base64, hashlib, json, random, re, time
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def md5_text(s):
    if not isinstance(s, str):
        s = str(s)
    return hashlib.md5(s.encode('utf-8')).hexdigest()


def get_content(url, args, site_json, save_debug=False):
    # https://github.com/ytdl-org/youtube-dl/blob/master/youtube_dl/extractor/anvato.py
    # https://w3.mp.lura.live/player/prod/v3/anvload.html?key=eyJtIjoiY2JzIiwidiI6ImFkc3REQW1yZ1JuZ09xM0wiLCJhbnZhY2siOiI1VkQ2RXlkNmRqZXdiQ21Od0JGbnNKajE3WUF2R1J3bCIsInNoYXJlTGluayI6Imh0dHBzOi8vY2JzbG9jLmFsLzNETUs1amsiLCJwbHVnaW5zIjp7ImNvbXNjb3JlIjp7ImNsaWVudElkIjoiMzAwMDAyMyIsImMzIjoicGhpbGFkZWxwaGlhLmNic2xvY2FsLmNvbSJ9LCJkZnAiOnsiY2xpZW50U2lkZSI6eyJhZFRhZ1VybCI6Imh0dHA6Ly9wdWJhZHMuZy5kb3VibGVjbGljay5uZXQvZ2FtcGFkL2Fkcz9zej0yeDImaXU9LzQxMjgvQ0JTLlBISUxMWSZjaXVfc3pzJmltcGw9cyZnZGZwX3JlcT0xJmVudj12cCZvdXRwdXQ9eG1sX3Zhc3QyJnVudmlld2VkX3Bvc2l0aW9uX3N0YXJ0PTEmdXJsPVtyZWZlcnJlcl91cmxdJmRlc2NyaXB0aW9uX3VybD1bZGVzY3JpcHRpb25fdXJsXSZjb3JyZWxhdG9yPVt0aW1lc3RhbXBdIiwia2V5VmFsdWVzIjp7ImNhdGVnb3JpZXMiOiJbW0NBVEVHT1JJRVNdXSIsInByb2dyYW0iOiJbW1BST0dSQU1fTkFNRV1dIiwic2l0ZVNlY3Rpb24iOiJ2aWRlby1leHBlcmllbmNlIiwiY2hhbm5lbElkIjoiY2g0NjUifX19LCJtb2F0Ijp7ImNsaWVudFNpZGUiOnsicGFydG5lckNvZGUiOiJjYnNsb2NhbGFudmF0b3ZpZGVvMTgxNzMyNjA5NDMxIn19LCJoZWFydGJlYXRCZXRhIjp7ImFjY291bnQiOiJjYnNsb2NhbC1nbG9iYWwtdW5pZmllZCxjYnNsb2NhbC1tYXJrZXQtcGhpbGFkZWxwaGlhLXVuaWZpZWQsY2JzbG9jYWwtc3RhdGlvbi1waGlsYWRlbHBoaWEtdSIsInB1Ymxpc2hlcklkIjoiY2JzbG9jYWwiLCJqb2JJZCI6InNjX3ZhIiwibWFya2V0aW5nQ2xvdWRJZCI6IjgyM0JBMDMzNTU2NzQ5N0Y3RjAwMDEwMUBBZG9iZU9yZyIsInRyYWNraW5nU2VydmVyIjoiY2JzZGlnaXRhbG1lZGlhLmhiLm9tdHJkYy5uZXQiLCJjdXN0b21UcmFja2luZ1NlcnZlciI6ImNic2RpZ2l0YWxtZWRpYS5kMS5zYy5vbXRyZGMubmV0IiwiY2hhcHRlclRyYWNraW5nIjpmYWxzZSwidmVyc2lvbiI6IjEuNSIsImN1c3RvbU1ldGFkYXRhIjp7InZpZGVvIjp7ImNic19tYXJrZXQiOiJjYnMtbG9jYWwuZ28tdmlwLmNvIiwiY2JzX3BsYXRmb3JtIjoiZGVza3RvcCJ9fSwicHJvZmlsZSI6ImNicyIsImN1c3RvbVRyYWNraW5nU2VydmVyU2VjdXJlIjoiY2JzZGlnaXRhbG1lZGlhLmQxLnNjLm9tdHJkYy5uZXQifX0sImh0bWw1Ijp0cnVlLCJ0b2tlbiI6ImRlZmF1bHQifQ%3D%3D
    # https://w3.mp.lura.live/player/prod/v3/anvload.html?key=eyJhdXRvcGxheSI6dHJ1ZSwiZXhwZWN0X3ByZXJvbGwiOnRydWUsInBsdWdpbnMiOnsiY29tc2NvcmUiOnsiY2xpZW50SWQiOiI2MDM2NDM5IiwiYzMiOiJ3a3JuLmNvbSIsInNjcmlwdCI6IlwvXC93My5tcC5sdXJhLmxpdmVcL3BsYXllclwvcHJvZFwvdjNcL3BsdWdpbnNcL2NvbXNjb3JlXC9jb21zY29yZXBsdWdpbi5taW4uanMiLCJ1c2VEZXJpdmVkTWV0YWRhdGEiOnRydWUsIm1hcHBpbmciOnsidmlkZW8iOnsiYzMiOiJ3a3JuLmNvbSIsIm5zX3N0X3N0Ijoid2tybiIsIm5zX3N0X3B1IjoiTmV4c3RhciIsIm5zX3N0X2dlIjoiTmV3cyxOZXdzLExvY2FsIE5ld3MiLCJjc191Y2ZyIjoiIn0sImFkIjp7ImMzIjoid2tybi5jb20iLCJuc19zdF9zdCI6Indrcm4iLCJuc19zdF9wdSI6Ik5leHN0YXIiLCJuc19zdF9nZSI6Ik5ld3MsTmV3cyxMb2NhbCBOZXdzIiwiY3NfdWNmciI6IiJ9fX0sImRmcCI6eyJhZFRhZ1VybCI6Imh0dHBzOlwvXC9wdWJhZHMuZy5kb3VibGVjbGljay5uZXRcL2dhbXBhZFwvYWRzP3N6PTF4MTAwMCZpdT1cLzU2NzhcL21nLndrcm5cL25ld3NcL21pZGRsZV90blwvbmFzaHZpbGxlJmltcGw9cyZnZGZwX3JlcT0xJmVudj12cCZvdXRwdXQ9dm1hcCZ1bnZpZXdlZF9wb3NpdGlvbl9zdGFydD0xJmFkX3J1bGU9MSZkZXNjcmlwdGlvbl91cmw9aHR0cHM6XC9cL3d3dy53a3JuLmNvbVwvbmV3c1wvbG9jYWwtbmV3c1wvbmFzaHZpbGxlXC9yYXRzLXJvYWNoZXMtdHJhc2gtcHJvYmxlbXMtbW91bnQtdXAtZm9yLXJlc2lkZW50c1wvYW1wXC8mdmNvbnA9MiZjdXN0X3BhcmFtcz12aWQlM0Q3Mzk3NDYwJTI2Y21zaWQlM0Q5Njg0MzElMjZwaWQlM0Q5Njg0MzElMjZwZXJzX2NpZCUzRG54cy03My1hcnRpY2xlLTk2ODQzMSUyNnZpZGNhdCUzRFwvbmV3c1wvbWlkZGxlX3RuXC9uYXNodmlsbGUlMjZib2JfY2slM0RbYm9iX2NrX3ZhbF0lMjZkX2NvZGUlM0RuYTAwMyUyNnBhZ2V0eXBlJTNEYW1wIn0sIm5pZWxzZW4iOnsiYXBpZCI6IlA2OTA5NkJFNy1DN0U5LTQxRDktODZGMi0xRjFBQzI1Q0Y4MEIiLCJzZmNvZGUiOiJkY3IiLCJ0eXBlIjoiZGNyIiwiYXBuIjoiQW52YXRvIiwiZW52aXJvbm1lbnQiOiJwcm9kdWN0aW9uIiwidXNlRGVyaXZlZE1ldGFkYXRhIjp0cnVlLCJtYXBwaW5nIjp7ImFkbG9hZHR5cGUiOjIsImFkTW9kZWwiOjJ9fSwic2VnbWVudEN1c3RvbSI6eyJzY3JpcHQiOiJodHRwczpcL1wvc2VnbWVudC5wc2cubmV4c3RhcmRpZ2l0YWwubmV0XC9hbnZhdG8uanMiLCJ3cml0ZUtleSI6Ijc2YnM2alZMemV1eDh2ZkJVUHlmWXM2cVJNdTkyalNGIiwicGx1Z2luc0xvYWRpbmdUaW1lb3V0IjoxMiwidWRsIjp7ImNvbnRlbnQiOnsidGl0bGUiOiJSYXRzLCByb2FjaGVzLCB0cmFzaCBwcm9ibGVtcyBtb3VudCB1cCBmb3IgcmVzaWRlbnRzIiwicHJpbWFyeUNhdGVnb3J5IjoiTmFzaHZpbGxlIiwicGFnZUlkIjo5Njg0MzEsInBhZ2VUeXBlIjoiYW1wIiwicGVyc2lzdGVudElkIjoibnhzLTczLWFydGljbGUtOTY4NDMxIiwibG9jYWxJZCI6Im54cy03My1hcnRpY2xlLTk2ODQzMSIsImF1dGhvck5hbWUiOiJTdGVwaGFuaWUgTGFuZ3N0b24iLCJhdXRob3JOb25CeWxpbmUiOiIifSwicGFnZSI6eyJhbXBVcmwiOiJodHRwczpcL1wvd3d3Lndrcm4uY29tXC9uZXdzXC9sb2NhbC1uZXdzXC9uYXNodmlsbGVcL3JhdHMtcm9hY2hlcy10cmFzaC1wcm9ibGVtcy1tb3VudC11cC1mb3ItcmVzaWRlbnRzXC9hbXBcLyJ9LCJzaXRlIjp7ImJyYW5kTmFtZSI6IldLUk4gTmV3cyAyIiwiY2FsbFNpZ24iOiJXS1JOIn19fX0sImFjY2Vzc0tleSI6InEyNjFYQW0ycUtFS251MXBxckhyUnNZbU8xazRQbU1CIiwidG9rZW4iOiJleUowZVhBaU9pSktWMVFpTENKaGJHY2lPaUpJVXpJMU5pSjkuZXlKMmFXUWlPaUkzTXprM05EWXdJaXdpYVhOeklqb2ljVEkyTVZoQmJUSnhTMFZMYm5VeGNIRnlTSEpTYzFsdFR6RnJORkJ0VFVJaUxDSmxlSEFpT2pFMk5ETXlOVGM1TVRWOS5TV19TZEJ4XzlBT0Q0dlljd1ZSdzdLRzZRRVA3TTBXSGdJT0d5RVFOZjdjIiwiZXhwZWN0UHJlcm9sbFRpbWVvdXQiOjgsIm54cyI6eyJtcDRVcmwiOiJodHRwczpcL1wvdGt4Lm1wLmx1cmEubGl2ZVwvcmVzdFwvdjJcL21jcFwvdmlkZW9cLzczOTc0NjA/YW52YWNrPTFQOFhuUU1ua3JFSzlmMWFtRUhCT0ZidzVQOUFtcmVEJnRva2VuPSU3RTZTdXdkcGNCYlVTNU15MVdaVmFtVmJsb0dzZVp2bzcwTVElM0QlM0QiLCJlbmFibGVGbG9hdGluZ1BsYXllciI6dHJ1ZX0sImRpc2FibGVNdXRlZEF1dG9wbGF5IjpmYWxzZSwicmVjb21tZW5kYXRpb25zIjp0cnVlLCJleHBlY3RQcmVyb2xsIjp0cnVlLCJ0aXRsZVZpc2libGUiOnRydWUsInBhdXNlT25DbGljayI6dHJ1ZSwidHJhY2tUaW1lUGVyaW9kIjo2MCwicCI6ImRlZmF1bHQiLCJtIjoiTElOIiwidiI6IjczOTc0NjAiLCJ3aWR0aCI6NjQwLCJoZWlnaHQiOjM2MH0=
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    query = parse_qs(split_url.query)
    if not query.get('key'):
        logger.warning('unhandled url with no key in ' + url)
        return None
    key_str = base64.b64decode(unquote(query['key'][0])).decode("utf-8")
    key_json = json.loads(key_str)
    if save_debug:
        utils.write_file(key_json, './debug/lura.json')
    video_id = ''
    anvack = ''
    token = ''
    if key_json.get('v'):
        video_id = key_json['v']
    if key_json.get('token'):
        token = key_json['token']
    if key_json.get('anvack'):
        anvack = key_json['anvack']
    elif key_json.get('accessKey'):
        anvack = key_json['accessKey']
    # elif key_json.get('nxs') and key_json['nxs'].get('mp4Url'):
    #     mp4_split_url = urlsplit(key_json['nxs']['mp4Url'])
    #     mp4_paths = list(filter(None, mp4_split_url.path[1:].split('/')))
    #     mp4_query = parse_qs(mp4_split_url.query)
    #     if not video_id and 'video' in mp4_paths:
    #         video_id = mp4_paths[-1]
    #     if mp4_query.get('anvack'):
    #         anvack = mp4_query['anvack'][0]
    if not video_id or not anvack:
        logger.warning('lura key does not have the expected data in ' + url)
        return None

    revision = ''
    version = ''
    built = ''
    api_key = ''
    page_html = utils.get_url_html(url)
    if page_html:
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', attrs={"src": re.compile(r'anvplayer\.min\.js')})
        if el:
            m = re.search(r'([^/]+)/scripts/anvplayer.min.js', el['src'])
            if m:
                revision = m.group(1)
                anvplayer_js = utils.get_url_html('{}://{}/{}/{}'.format(split_url.scheme, split_url.netloc, '/'.join(paths[:-1]), el['src']))
                if anvplayer_js:
                    m = re.search(r'\w\.version="([^"]+)",\w\.built="([^"]+)",\w\.revision="{}"'.format(revision), anvplayer_js)
                    if m:
                        version = m.group(1)
                        built = m.group(2)
                    m = re.search(r'apikey=([^"]+)', anvplayer_js)
                    if m:
                        api_key = m.group(1)
    if not revision or not version or not built or not api_key:
        logger.warning('unable to parse variables from anvplayer.js in ' + url)
        return None

    access_url = 'https://access.mp.lura.live/anvacks/{}?apikey={}'.format(anvack, api_key)
    access_json = utils.get_url_json(access_url)
    if access_json:
        server_time_url = access_json['api']['time']
        video_data_url = access_json['api']['video']
    else:
        server_time_url = 'https://tkx.mp.lura.live/rest/v2/server_time?anvack={{ANVACK}}'
        video_data_url = 'https://tkx.mp.lura.live/rest/v2/mcp/video/{{VIDEO_ID}}?anvack={{ANVACK}}'

    server_time_url = server_time_url.replace('{{VIDEO_ID}}', video_id).replace('{{ANVACK}}', anvack)
    anvtrid = 'w{}{}'.format(revision, md5_text(time.time()*1000)[-24:])
    server_time_url += '&anvtrid=' + anvtrid
    server_time_json = utils.get_url_json(server_time_url)
    if not server_time_json:
         logger.warning('error getting server time from ' + server_time_url)
         return None
    server_time = int(server_time_json['server_time'])
    time_delta = 1000*server_time - 1000*time.time()

    video_data_url = video_data_url.replace('{{VIDEO_ID}}', video_id).replace('{{ANVACK}}', anvack)
    anvtrid = 'w{}{}'.format(revision, md5_text(1000*time.time())[-24:])
    video_data_url += '&anvtrid=' + anvtrid

    ts = time.time()*1000
    input_data = '{}~{}~{}'.format(ts, md5_text(video_data_url), md5_text('{}'.format(ts)))
    # TODO: parse from anvplayer_js
    key = '31c242849e73a0ce'
    #padded_data = pad(input_data[:64].encode(), 16)
    padded_data = input_data[:64].encode('utf-8')
    cipher = AES.new(key.encode('utf-8'), AES.MODE_ECB)
    enc_data = cipher.encrypt(padded_data)
    b64enc_data = base64.b64encode(enc_data)

    video_data_url += '&rtyp=fp&X-Anvato-Adst-Auth={}'.format(b64enc_data.decode('utf-8').replace('=', '%3D'))
    t = list("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
    n = [None] * 36
    for i in range(36):
        if i in [8, 13, 18, 23]:
            n[i] = "-"
        elif i == 14:
            n[i] = "4"
        else:
            if i == 19:
                e = random.randint(0, 3) | 8
            else:
                e = random.randint(0, 15)
            n[i] = t[e]
    device_id = ''.join(n)
    anvrid = md5_text(1000*time.time() * random.random())[:30]
    anvts = round((1000*time.time() + time_delta) / 1000)
    post_data = {
        "ads": {
            "freewheel": {}
        },
        "content": {
            "mcp_video_id": video_id,
            "mpx_guid": ""
        },
        "user": {
            "glg": "",
            "glt": "",
            "gst": "",
            "gzip": "",
            "hst": "",
            "device": "web",
            "device_id": device_id,
            "sdkver": "{}.{}.{}".format(version, built, revision),
            "sdkenv": "html5",
            "adobepass": {
                "requestor": "",
                "resource": ""
            },
            "mvpd_authorization": {}
        },
        "api": {
            "anvrid": anvrid,
            "anvts": anvts
        }
    }
    if token:
        post_data['api']['anvstk2'] = token
    else:
        post_data['api']['anvstk2'] = 'default'
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Not.A/Brand\";v=\"8\", \"Chromium\";v=\"114\", \"Microsoft Edge\";v=\"114\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site"
    }
    video_data = utils.post_url(video_data_url, json_data=post_data, headers=headers, r_text=True)
    if not video_data:
        return None
    i = video_data.find('{')
    j = video_data.rfind('}')
    video_json = json.loads(video_data[i:j+1])
    if save_debug:
        utils.write_file(video_json, './debug/video.json')

    item = {}
    item['id'] = video_id
    if key_json.get('shareLink'):
        item['url'] = key_json['shareLink']
    if video_json.get('def_title'):
        item['title'] = video_json['def_title']
    elif video_json.get('def_descriptions'):
        item['title'] = video_json['def_description']
    if video_json.get('program_name'):
        item['author'] = {"name": video_json['program_name']}
    if video_json.get('ts_airdate'):
        dt = datetime.fromtimestamp(int(video_json['ts_airdate'])).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
    if video_json.get('src_image_url') and utils.url_exists(video_json['src_image_url']):
        item['_image'] = video_json['src_image_url']
        poster = item['_image']
    elif video_json.get('src_logo_url') and utils.url_exists(video_json['src_logo_url']):
        item['_image'] = video_json['src_logo_url']
        poster = item['_image']
    else:
        poster = ''
    if item.get('title'):
        caption = item['title']
    else:
        caption = ''
    for video in video_json['published_urls']:
        if video['format'] == 'm3u8-variant':
            m3u8_json = utils.get_url_json(video['embed_url'])
            if m3u8_json:
                item['_video'] = m3u8_json['master_m3u8']
                item['_video_type'] = 'application/x-mpegURL'
            else:
                item['_video'] = video['embed_url']
                item['_video_type'] = 'application/x-mpegURL'
            item['content_html'] = utils.add_video(item['_video'], item['_video_type'], poster, caption)
    return item
