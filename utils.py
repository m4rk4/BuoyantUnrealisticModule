import base64, feedparser, json, math, os, random, re, requests, string
from bs4 import BeautifulSoup
from datetime import datetime
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from urllib.parse import quote_plus, unquote, urlsplit

from feedhandlers import vimeo, youtube

import logging
logger = logging.getLogger(__name__)

# https://www.peterbe.com/plog/best-practice-with-retries-with-requests
# https://findwork.dev/blog/advanced-usage-python-requests-timeouts-retries-hooks/#retry-on-failure
def requests_retry_session(retries=4, proxies=None):
  session = requests.Session()
  if proxies:
    session.proxies.update(proxies)
  retry = Retry(
    total=retries,
    read=retries,
    connect=retries,
    backoff_factor=1,
    status_forcelist=[404, 429, 500, 502, 503, 504],
    method_whitelist=["HEAD", "GET", "OPTIONS"]
  )
  adapter = HTTPAdapter(max_retries=retry)
  session.mount('http://', adapter)
  session.mount('https://', adapter)
  return session

def get_request(url, user_agent, headers=None, retries=3, use_proxy=False):
  if user_agent == 'desktop':
    ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Safari/537.36'
  elif user_agent == 'mobile':
    ua = 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1'
  else: # Googlebot
    ua = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'

  if headers:
    if headers.get('user-agent'):
      headers['user-agent'] = ua
  else:
    headers = {}
    headers['user-agent'] = ua

  n = 0
  r = None
  while not r and n < 2:
    if n == 0:
      # First time us proxy if specified
      if use_proxy:
        proxies = {"http": "http://69.167.174.17"}
      else:
        proxies = None
    else:
      # Second time, try the proxy
      proxies = {"http": "http://69.167.174.17"}
    try:
      r = requests_retry_session(retries, proxies).get(url, headers=headers, timeout=10)
      r.raise_for_status()
    except Exception as e:
      logger.warning('request error {} getting {}'.format(e.__class__.__name__, url))
    n += 1
  return r

def get_url_json(url, user_agent='desktop', headers=None, retries=3, use_proxy=False):
  r = get_request(url, user_agent, headers, retries, use_proxy)
  if r:
    try:
      return r.json()
    except:
      logger.warning('error converting response to json from request {}'.format(url))
      if False:
        with open('./debug/debug.txt', 'w', encoding='utf-8') as f:
          f.write(r.text)
  return None

def get_url_html(url, user_agent='googlebot', headers=None, retries=3, use_proxy=False):
  r = get_request(url, user_agent, headers, retries, use_proxy)
  if r:
    return r.text
  return None

def get_url_title_desc(url):
  html = get_url_html(url)
  if html:
    soup = BeautifulSoup(html, 'html.parser')
    el = soup.find('title')
    if el:
      title = el.get_text()
    else:
      title = it['url']
    el = soup.find('meta', attrs={"name": "description"})
    if el:
      desc = el['content']
    else:
      desc = None
  else:
    title = it['url']
    desc = None
  return title, desc

def post_url(url, data, headers=None):
  try:
    if headers:
      r = requests.post(url, headers=headers, json=data)
    else:
      r = requests.post(url, json=data)
    r.raise_for_status()
  except requests.exceptions.HTTPError as e:
    status_code = e.response.status_code
    logger.warning('HTTPError {} requesting {}'.format(e.response.status_code, url))
    # 402 Payment Required. Try skipping and processing the json anyway.
    if status_code != 402:
      return None
  except requests.exceptions.ConnectionError:
    logger.warning('ConnectionError requesting {}'.format(url))
    return None
  except requests.exceptions.Timeout:
    logger.warning('Timeout error requesting {}'.format(url))
    return None
  try:
    return r.json()
  except:
    logger.warning('error converting to json: {}'.format(url))
  return None

def url_exists(url):
  r = requests.head(url)
  return r.status_code == requests.codes.ok

def write_file(data, filename):
  if filename.endswith('.json'):
    with open(filename, 'w', encoding='utf-8') as file:
      json.dump(data, file, indent=4)
  else:
    with open(filename, 'w', encoding='utf-8') as f:
      f.write(data)
  return

def read_json_file(json_filename):
  json_file = None
  if os.stat(json_filename).st_size > 0:
    with open(json_filename) as f:
      json_file = json.load(f)
  else:
    logger.warning('empty file {}'.format(json_filename))
  return json_file

def closest_value(lst, target):
  return lst[min(range(len(lst)), key = lambda i: abs(int(lst[i]) - target))]

def closest_dict(lst, k, target):
  print(lst)
  return lst[min(range(len(lst)), key = lambda i: abs(int(lst[i][k]) - target))]

def clean_url(url):
  split_url = urlsplit(url)
  return '{}://{}{}'.format(split_url.scheme, split_url.netloc, split_url.path)

def clean_referral_link(link):
  if '/assoc-redirect.amazon.com' in link:
    m = re.search(r'\/(https:\/\/www\.amazon\.com\/dp\/\w+)', link)
    if m:
      return m.group(1)
  elif 'anrdoezrs.net' in link:
    m = re.search(r'\/(https?:\/\/.*)', link)
    if m:
      return m.group(1)
  else:
    for it in urlsplit(link).query.split('&'):
      m = re.search(r'=(https?(%|:).*)', it)
      if m:
        return clean_referral_link(unquote(m.group(1)))
  return link

def init_jsonfeed(args):
  parsed = urlsplit(args['url'])

  feed = {}
  feed['version'] = 'https://jsonfeed.org/version/1'

  # Title is required
  if 'title' in args:
    feed['title'] = args['title']
  else:
    feed['title'] = parsed.netloc

  if 'home_page_url' in args:
    feed['home_page_url'] = args['home_page_url']
  else:
    feed['home_page_url'] = '{}://{}'.format(parsed.scheme, parsed.netloc)

  feed['items'] = []
  return feed

def random_alphanumeric_string(str_len=8):
  letters_digits = string.ascii_letters + string.digits
  return ''.join((random.choice(letters_digits) for i in range(str_len)))

def check_regex_filter(item, filters):
  # Note: any match returns True
  # TODO: handle cases where all filters must match

  # Simple conversion to Python style regex
  # Note: filter should a dict of form: {'tag': '/regex/i'}
  # - Remove begining and ending /'s
  # - Check for flags - only 'i' supported now
  for tag in filters.keys():
    m = re.match(r"^/(.*)/(i?)$", filters[tag])
    pattern = m.group(1)
    flags = 0
    if m.group(2) == 'i':
      flags = re.I
    r = re.compile(pattern, flags)

    # Handle lists & strings
    if tag in item:
      if isinstance(item[tag], list):
        m = list(filter(r.match, item[tag]))
        if m:
          return True
      else:
        m = r.match(item[tag])
        if m:
          return True

  # No matches
  return False

def check_age(item, args):
  # Check item age (in hours)
  # Return: True if item timestamp is less than the specified age
  #         False if item timestamp is older than specified age
  # If no item is specified return False
  # If there's no age or timestamp returns True
  if not item:
    return False
  if item.get('_timestamp') and args.get('age'):
    now = datetime.utcnow().timestamp()
    if (now - item['_timestamp'])/3600 > float(args['age']):
      return False
  return True

def filter_item(item, args):
  # Returns:
  #  True = include the item
  #  False = exclude the item

  # Check item age (in hours)
  # Note: age overrides other filters
  if not check_age(item, args):
    return False

  # Note: A matched exclude filter will take precedent over a matched include filter
  # Check exclude filters
  if 'exc_filters' in args:
    filters = json.loads(args['exc_filters'])
    exc = check_regex_filter(item, filters)
    if exc == True:
      return False

  # Check include filters
  if 'inc_filters' in args:
    filters = json.loads(args('inc_filters'))
    inc = check_regex_filter(item, filters)
    if inc == False:
      return False

  return True

def bs_get_inner_html(soup):
  html = ''
  for child in soup.children:
    html += str(child)
  return html

def add_blockquote(text):
  return '<blockquote style="border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;">{}</blockquote>'.format(text)

def open_pullquote():
  #return '<span style="font-size: 1.5em; line-height: 0.67em; color: lightgrey;">&#x275D;</span><span style="font-style: italic; line-height: 1em;">'
  return '<blockquote><svg version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" x="0px" y="0px" viewBox="0 0 46.195 46.195" transform="rotate(180)" style="height:1em;"><g><path style="fill:#010002;" d="M35.765,8.264c-5.898,0-10.555,4.782-10.555,10.68s4.844,10.68,10.742,10.68 c0.059,0,0.148-0.008,0.207-0.009c-2.332,1.857-5.261,2.976-8.467,2.976c-1.475,0-2.662,1.196-2.662,2.67s0.949,2.67,2.424,2.67 c10.469-0.001,18.741-8.518,18.741-18.987c0-0.002,0-0.004,0-0.007C46.195,13.042,41.661,8.264,35.765,8.264z"/><path style="fill:#010002;" d="M10.75,8.264c-5.898,0-10.563,4.782-10.563,10.68s4.84,10.68,10.739,10.68 c0.059,0,0.146-0.008,0.205-0.009c-2.332,1.857-5.262,2.976-8.468,2.976C1.188,32.591,0,33.787,0,35.261s0.964,2.67,2.439,2.67 c10.469-0.001,18.756-8.518,18.756-18.987c0-0.002,0-0.004,0-0.007C21.195,13.042,16.646,8.264,10.75,8.264z"/></g></svg><em>'

def close_pullquote(author=''):
  #return '</span><span style="font-size: 1.5em; line-height: 0.67em; color: lightgrey;">&#x2760;</span>'
  end_html = '</em>&nbsp;<svg version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" x="0px" y="0px" viewBox="0 0 46.195 46.195" style="height:1em;"><g><path style="fill:#010002;" d="M35.765,8.264c-5.898,0-10.555,4.782-10.555,10.68s4.844,10.68,10.742,10.68 c0.059,0,0.148-0.008,0.207-0.009c-2.332,1.857-5.261,2.976-8.467,2.976c-1.475,0-2.662,1.196-2.662,2.67s0.949,2.67,2.424,2.67 c10.469-0.001,18.741-8.518,18.741-18.987c0-0.002,0-0.004,0-0.007C46.195,13.042,41.661,8.264,35.765,8.264z"/><path style="fill:#010002;" d="M10.75,8.264c-5.898,0-10.563,4.782-10.563,10.68s4.84,10.68,10.739,10.68 c0.059,0,0.146-0.008,0.205-0.009c-2.332,1.857-5.262,2.976-8.468,2.976C1.188,32.591,0,33.787,0,35.261s0.964,2.67,2.439,2.67 c10.469-0.001,18.756-8.518,18.756-18.987c0-0.002,0-0.004,0-0.007C21.195,13.042,16.646,8.264,10.75,8.264z"/></g></svg>'
  if author:
    end_html += '<br /><small>&mdash;&nbsp;{}</small>'.format(author)
  end_html += '</blockquote>'
  return end_html

def add_pullquote(quote, author=''):
  # Strip quotes
  if (quote.startswith('"') or quote.startswith('“')) and (quote.endswith('"') or quote.endswith('”')):
    quote = quote[1:-1]
  pullquote = open_pullquote() + quote + close_pullquote(author)
  return pullquote

def add_image(img_src, caption=None, width=None, height=None, attr=None, background='', link='', gawker=False):
  if width:
    img_width = 'width="{}"'.format(width)
  else:
    img_width = 'width="100%"'

  if height:
    img_height = ' height="{}"'.format(height)
  else:
    img_height = ''

  if attr:
    img_attr = ' {}'.format(attr)
  else:
    img_attr = ''

  if background:
    bg_style = ' style="background:url({});"'.format(background)
  else:
    bg_style = ''

  begin_html = '<figure>'
  if link:
    begin_html += '<a href="{}">'.format(link)
  begin_html += '<img {}{}{}{} src="{}" />'.format(img_width, img_height, img_attr, bg_style, img_src)
  if link:
    begin_html += '</a>'
  end_html = '</figure>'

  if caption:
    begin_html += '<figcaption><small>' + caption
    end_html = '</small></figcaption></figure>'

  if gawker:
    return begin_html, end_html

  return begin_html + end_html

def add_audio(audio_src, audio_type, poster='', title='', desc='', link=''):
  if not poster and not title and not desc:
    return '<center><audio controls><source type="{0}" src="{1}"></source><a href="{1}">Your browser does not support the audio tag.</audio><small>Play track</small></a></center>'.format(audio_type, audio_src)

  audio_html = ''
  rows = 1
  if title:
    rows += 1
    if link:
      audio_html += '<tr><td><a href="{}"><b>{}</b></a></td></tr>'.format(link, title)
    else:
      audio_html += '<tr><td><b>{}</b></td></tr>'.format(title)

  if desc:
    rows += 1
    audio_html += '<tr><td><small>{}</small></td></tr>'.format(desc)

  audio_html += '<tr><td><audio controls><source type="{0}" src="{1}"></source>Your browser does not support the audio tag.</audio><br /><a href="{1}"><small>Play track</small></a></td></tr>'.format(audio_type, audio_src)

  if poster:
    audio_html = '<tr><td width="30%" rowspan="{}"><img width="100%" src="{}"></td>'.format(rows, poster) + audio_html[4:]

  audio_html = '<center><table style="width:480px; border:1px solid black; border-radius:10px; border-spacing:0;">' + audio_html
  audio_html += '</table></center>'

  return audio_html

def add_megaphone(url):
  split_url = urlsplit(url)
  m = re.search(r'e=(\w+)', split_url.query)
  if not m:
    logger.warning('unable to parse ' + url)
    return ''
  data_json = get_url_json('https://player.megaphone.fm/playlist/episode/' + m.group(1))
  if not data_json:
    logger.warning('unable to parse ' + url)
    return ''
  return add_audio(data_json['episodes'][0]['audioUrl'], 'audio/mpeg', data_json['episodes'][0]['imageUrl'], data_json['episodes'][0]['title'], data_json['episodes'][0]['subtitle'], data_json['episodes'][0]['dataClipboardText'])

def add_video(video_url, video_type, poster='', caption='', width=640, height=360, gawker=False):
  if not poster:
    poster = 'https://BuoyantUnrealisticModule.m4rk4.repl.co/static/video_poster-640x360.webp'

  h = round(height/width*100, 2)

  if video_type == 'video/mp4' or video_type == 'video/webm':
    video_src = video_url
    video_html = '<video width="100%" controls poster="{}" crossorigin="anonymous"><source src="{}" type="{}"></video>'.format(poster, video_src, video_type)
  elif video_type == 'application/x-mpegURL':
    video_src = 'https://BuoyantUnrealisticModule.m4rk4.repl.co/video?src={}&video_type={}&poster={}'.format(quote_plus(video_url), quote_plus(video_type), quote_plus(poster))
    video_html = '<div style="overflow:hidden; position:relative; padding-top:{}%;"><iframe style="width:100%; height:100%; position:absolute; left:0; top:0;" frameBorder="0" src="{}" scrolling="no" allowfullscreen></iframe></div>'.format(h, video_src)
  elif video_type == 'vimeo':
    content = vimeo.get_content(video_url, None, False)
    if content.get('_image'):
      poster = content['_image']
    video_src = 'https://BuoyantUnrealisticModule.m4rk4.repl.co/redirect?url={}'.format(quote_plus(video_url))
    caption = '{} | <a href="{}">Watch on Vimeo</a>'.format(content['title'], video_url)
    video_html = '<video width="100%" controls poster="{}" crossorigin="anonymous"><source src="{}" type="video/mp4"></video>'.format(content['_image'], video_src)
  elif video_type == 'youtube':
    content = youtube.get_content(video_url, None, False)
    if content.get('_image'):
      poster = content['_image']
    video_src = 'https://BuoyantUnrealisticModule.m4rk4.repl.co/redirect?url={}'.format(quote_plus(video_url))
    caption = '{} | <a href="{}">Watch on YouTube</a>'.format(content['title'], video_url)
    video_html = '<video width="100%" controls poster="{}" crossorigin="anonymous"><source src="{}" type="video/mp4"></video>'.format(content['_image'], video_src)
  elif video_type == 'iframe':
    video_html = '<div style="overflow:hidden; position:relative; padding-top:{}%;"><iframe style="width:100%; height:100%; position:absolute; left:0; top:0;" frameBorder="0" src="{}" scrolling="no" allowfullscreen></iframe></div>'.format(h, video_url)
  else:
    logger.warning('unknown video type {} for {}'.format(video_type, video_url))
    return ''

  if caption:
    caption += ' | '
  caption += '<a href="{}">Open video</a>'.format(video_src)

  #begin_html = '<table style="width:100%; max-height:480px; margin-right:auto; margin-left:auto;"><tr><td><center>{}</center></td></tr><tr><td><small>'.format(video_html)
  #end_html = caption + '</small></td></tr></table>'
  #begin_html = video_html + '<div><small>'
  #end_html = caption + '</small></div>'
  #if gawker:
  #  return begin_html, end_html
  #return begin_html + end_html
  return add_image(poster, caption, link=video_src, gawker=gawker)

def add_youtube(ytstr, width=None, height=None, caption='', gawker=False):
  # ytstr can be either:
  # - the 11 digit id only, e.g. D4gPQDyOixQ
  # - the watch url, e.g. https://www.youtube.com/watch?v=D4gPQDyOixQ
  # - the embed url, e.g. https://www.youtube.com/embed/D4gPQDyOixQ
  # - the short url, e.g. https://yout.be/D4gPQDyOixQ
  yt_id = ''
  if 'https' in ytstr:
    if 'youtube' in ytstr:
      # Watch url 
      m = re.search(r'youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})', ytstr)
      if m:
        yt_id = m.group(1)
      else:
        # Embed url
        m = re.search(r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})', ytstr)
        if m:
          yt_id = m.group(1)

      # In the case of an iframe, extract the for width & height to get the proper aspect ratio
      if 'iframe' in ytstr:
        m = re.search(r'width="(\d+)"', ytstr)
        if m:
          width = int(m.group(1))
        m = re.search(r'height="(\d+)"', ytstr)
        if m:
          height = int(m.group(1))
    elif 'youtu.be' in ytstr:
      m = re.search(r'youtu\.be\/([a-zA-Z0-9_-]{11})', ytstr)
      if m:
        yt_id = m.group(1)
  elif len(ytstr) == 11:
    # id only
    yt_id = ytstr
  else:
    logger.warning('unknown Youtube embed ' + ytstr)
    return ''

  if not yt_id:
    logger.warning('Youtube id not found in ' + ytstr)
    return ''

  yt_url = 'https://www.youtube-nocookie.com/embed/{}'.format(yt_id)

  # Scale all to 640x360
  w = 640
  h = 360
  # maintain aspect ratio if width & height are given
  if width and height:
    h = math.ceil(w*int(height)/int(width))

  return add_video(yt_url, 'youtube', '', caption, w, h, gawker)

def add_youtube_playlist(yt_id, width=640, height=360):
  return '<center><iframe width="{}" height="{}"  src="https://www.youtube-nocookie.com/embed/videoseries?list={}" allow="encrypted-media" allowfullscreen></iframe></center>'.format(width, height, yt_id)

def add_vimeo(vimeo_str, width=None, height=None, caption='', gawker=False):
  # DOES NOT WORK
  # vimeo_str can be either:
  # - the id only, e.g. 545162250
  # - the Vimeo url, e.g. https://vimeo.com/545162250
  # - the player url, e.g. https://player.vimeo.com/video/545162250
  # - an embedded iframe (has a player url)
  vimeo_id = ''
  if 'https' in vimeo_str:
    # Vimeo url 
    m = re.search(r'vimeo\.com\/(\d+)', vimeo_str)
    if m:
      vimeo_id = m.group(1)
    else:
      # Player url
      m = re.search(r'player\.vimeo\.com\/video\/(\d+)', vimeo_str)
      if m:
        vimeo_id = m.group(1)
  else:
    vimeo_id = vimeo_str

  return add_video('https://vimeo.com/' + vimeo_id, 'vimeo', '', caption, gawker)

def add_tiktok(tiktok):
  # tiktok can be url or id
  if 'https' in tiktok:
    # Clean up the url
    split_url = urlsplit(tiktok)
    tiktok_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, split_url.path)
  else:
    # Video id. Note: the user doesn't matter here.
    tiktok_url = 'https://www.tiktok.com/@tiktok/video/{}'.format(tiktok)
  tiktok_json = get_url_json('https://www.tiktok.com/oembed?url=' + tiktok_url)
  if tiktok_json is None:
    return ''
  return '<div class="embed-tiktok">{}</div>'.format(tiktok_json['html'])

def add_instagram(igstr, save_debug=False):
  def format_caption_links(matchobj):
    if matchobj.group(1) == '#':
      return '<a href="https://www.instagram.com/explore/tags/{0}/">#{0}</a>'.format(matchobj.group(2))
    elif matchobj.group(1) == '@':
      return '<a href="https://www.instagram.com/{0}/">@{0}</a>'.format(matchobj.group(2))

  # Need to use a proxy to show images because of CORS
  imageproxy = 'https://bibliogram.snopyta.org/imageproxy?url='

  # igstr can be a url or id
  if 'https' in igstr:
    # Extract the post id
    m = re.search(r'instagram\.com\/([^\/]+)\/([^\/]+)', igstr)
    if m:
      ig_url = 'https://www.instagram.com/{}/{}/'.format(m.group(1), m.group(2))
    else:
      logger.warning('unable to parse instgram url {}'.format(igstr))
  else:
    ig_url = 'https://www.instagram.com/p/{}/'.format(igstr)

  ig_embed = get_url_html(ig_url + 'embed/captioned/?cr=1', 'desktop')
  if not ig_embed:
    return ''
  if save_debug:
    with open('./debug/debug.html', 'w', encoding='utf-8') as f:
      f.write(ig_embed)

  soup = BeautifulSoup(ig_embed, 'html.parser')

  m = re.search(r"window\.__additionalDataLoaded\('extra',(.+)\);<\/script>", ig_embed)
  if m:
    try:
      ig_data = json.loads(m.group(1))
    except:
      ig_data = None

  if ig_data:
    if save_debug:
      with open('./debug/debug.json', 'w') as f:
        json.dump(ig_data, f, indent=4)
    avatar = ig_data['shortcode_media']['owner']['profile_pic_url']
    username = ig_data['shortcode_media']['owner']['username']
  else:
    el = soup.find(class_='Avatar').img
    avatar = el['src']
    username = soup.find(class_='UsernameText').get_text()

  post_caption = '<hr /><a href="{}"><small>Open in Instagram</small></a>'.format(ig_url)

  caption = None
  if ig_data:
    try:
      caption = ig_data['shortcode_media']['edge_media_to_caption']['edges'][0]['node']['text']
    except:
      caption = None

    if caption:
      caption = caption.replace('\n', '<br />')
      caption = re.sub(r'(@|#)(\w+)', format_caption_links, caption)
      post_caption = '<hr />' + caption + post_caption

  if not caption:
    caption = soup.find(class_='Caption')
    if caption:
      # Make paragragh instead of div to help with spacing
      caption.name = 'p'

      # Remove username from beginning of caption
      el = caption.find('a', class_='CaptionUsername')
      if el and el.get_text() == username:
        el.decompose()

      # Remove comment section
      el = caption.find(class_='CaptionComments')
      if el:
        el.decompose()

      # Remove whitespace from start
      while caption.contents[0] == '\n' or caption.contents[0].name == 'br':
        caption.contents.pop(0)

      # Fix links
      for a in caption.find_all('a'):
        split_url = urlsplit(a['href'])
        if split_url.scheme:
          a_href = '{}://{}{}'.format(split_url.scheme, split_url.netloc, split_url.path)
        else:
          a_href = 'https://www.instagram.com' + split_url.path
        a.attrs = {}
        a['href'] = a_href
        a['style'] = 'text-decoration:none;'
        a.string = a.get_text()

      if str(caption):
        post_caption = '<hr />' + str(caption) + post_caption

  post_media = '<hr />'
  media_type = soup.find(class_='Embed')['data-media-type']
  if media_type == 'GraphImage':
    for el in soup.find_all('img', class_='EmbeddedMediaImage'):
      post_media += '<img width="100%" style="min-width:260px; max-width:560px;" src="{}"><br /><a href="{}"><small>Open image</small></a>'.format(imageproxy + quote_plus(el['src']), el['src'])
  elif media_type == 'GraphVideo':
    video_src = ''
    if ig_data:
      poster = imageproxy + quote_plus(ig_data['shortcode_media']['display_resources'][0]['src'])
      video_src = ig_data['shortcode_media']['video_url']
    else:
      el = soup.find('img', class_='EmbeddedMediaImage')
      if el:
        poster = imageproxy + quote_plus(el['src'])
    if video_src:
      post_media += '<video width="100%" style="min-width:260px; max-width:560px;" controls poster="{0}" crossorigin="anonymous"><source src="{1}" type="video/mp4"></video><br /><a href="{1}"><small>Open video</small></a>'.format(poster, video_src)
    else:
      post_media += '<img width="100%" style="min-width:260px; max-width:560px;" src="{}"><br /><a href="{}"><small>Watch on Instagram</small></a>'.format(poster, ig_url)
  elif media_type == 'GraphSidecar':
    if ig_data:
      n = 0
      for edge in ig_data['shortcode_media']['edge_sidecar_to_children']['edges']:
        if edge['node']['__typename'] == 'GraphImage':
          if n > 0:
            post_media += '<br /><br />'
          img_src = edge['node']['display_resources'][0]['src']
          post_media += '<img width="100%" style="min-width:260px; max-width:560px;" src="{}"><br /><a href="{}"><small>Open image</small></a>'.format(imageproxy + quote_plus(img_src), img_src)
        elif edge['node']['__typename'] == 'GraphVideo':
          if n > 0:
            post_media += '<br /><br />'
          poster = imageproxy + quote_plus(edge['node']['display_resources'][0]['src'])
          post_media += '<video width="100%" style="min-width:260px; max-width:560px;" controls poster="{0}" crossorigin="anonymous"><source src="{1}" type="video/mp4"></video><br /><a href="{1}"><small>Open video</small></a>'.format(poster, edge['node']['video_url'])
        n += 1
    else:
      logger.warning('Instagram GraphSidecar media without ig_data in ' + ig_url)

  ig_html = '<table style="min-width:300px; max-width:600px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:5px;">'
  ig_html += '<tr><td style="width:56px;"><img style="width:48px; height:48px; border-radius:50%;" src="{0}" /></td><td><a style="text-decoration:none;" href="https://www.instagram.com/{1}"><b>{1}</b></a></td></tr>'.format(imageproxy + quote_plus(avatar), username)
  if post_media:
    ig_html += '<tr><td colspan="2">{}</td></tr>'.format(post_media)
  if post_caption:
    ig_html += '<tr><td colspan="2">{}</td></tr>'.format(post_caption)
  ig_html += '</table>'

  return ig_html

def add_barchart(labels, values, title='', caption='', max_value=0, percent=True, border=True, width="75%"):
  color = 'rgb(196, 207, 214)'
  font = ''
  if max_value == 0:
    max_value = max(values)
  if border:
    border = ' border:1px solid black; border-radius:10px;'
  else:
    border = ''
  padding = ' padding-left:10px; padding-right:10px;'
  if title:
    padding += ' padding-top:0px;'
  else:
    padding += ' padding-top:10px;'
  if caption:
    padding += ' padding-bottom:0px;'
  else:
    padding += ' padding-bottom:10px;'
  graph_html = '<div style="width:{}; margin-left:auto; margin-right:auto;{}{}">'.format(width, padding, border)
  if title:
    graph_html += '<h3>{}</h3>'.format(title)
  n = len(labels)
  graph_html += '<svg xmlns="http://www.w3.org/2000/svg" style="width:95%; height:{}em; margin-left:auto; margin-right:auto;">'.format(2*n-0.5)
  for i in range(n):
    val = round(100*values[i]/max_value, 1)
    if percent:
      val_text = '{}%'.format(val)
    else:
      val_text = str(values[i])
    graph_html += '<g><rect x="0" y="{0}em" width="{1}%" height="1.1em" fill="{2}"></rect><text x="0.5em" y="{3}em"{4}>{5}</text><rect x="{1}%" y="{0}em" width="{6}%" height="1.1em" fill="none"></rect><text x="99%" y="{3}em" text-anchor="end">{7}</text></g>'.format(2*i, val, color, 2*i+0.9, font, labels[i], round(100-val, 1), val_text)
  graph_html += '</svg>'
  if caption:
    graph_html += '<div><small>{}</small></div>'.format(caption)
  graph_html += '</div>'
  return graph_html