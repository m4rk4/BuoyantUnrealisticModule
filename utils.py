import importlib, json, math, os, random, re, requests, string, tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from urllib.parse import parse_qs, quote_plus, urlsplit

import config
from feedhandlers import instagram, twitter, vimeo, youtube

import logging
logger = logging.getLogger(__name__)

def get_module(url, handler=''):
  sites_json = read_json_file('./sites.json')
  module = None
  module_name = ''
  if url:
    if 'wp-json' in url:
      module_name = '.wp_posts'
    else:
      tld = tldextract.extract(url.strip())
      if tld.domain == 'youtu' and tld.suffix == 'be':
        domain = 'youtu.be'
      elif tld.domain == 'megaphone' and tld.suffix == 'fm':
        domain = 'megaphone.fm'
      elif tld.domain == 'go':
        domain = tld.subdomain
      elif tld.domain == 'feedburner':
        domain = urlsplit(url).path.split('/')[1]
      else:
        domain = tld.domain
      if sites_json.get(domain):
        module_name = '.{}'.format(sites_json[domain]['module'])
  if handler and not module_name:
    module_name = '.{}'.format(handler)
  if module_name:
    try:
      module = importlib.import_module(module_name, 'feedhandlers')
    except:
      logger.warning('unable to load module ' + module_name)
      module = None
  else:
    logger.warning('unknown module for ' + url)
  return module

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
  elif user_agent == 'googlebot':
    ua = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
  else: # Googlebot
    ua = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'

  if headers:
    if headers.get('user-agent'):
      headers['user-agent'] = ua
  else:
    headers = {}
    headers['user-agent'] = ua

  if use_proxy:
    proxies = config.proxies
  else:
    proxies = None

  r = None
  for i in range(2):
    try:
      if proxies:
        verify = False
      else:
        verify = True
      r = requests_retry_session(retries, proxies).get(url, headers=headers, timeout=10, verify=verify)
      r.raise_for_status()
    except Exception as e:
      if r != None:
        if r.status_code == 402:
          return r
        else:
          status_code = ' status code {}'.format(r.status_code)
      else:
        status_code = ''
      logger.warning('request error {}{} getting {}'.format(e.__class__.__name__, status_code, url))
      r = None
    if r:
      break
    else:
      # Try again using the proxy
      proxies = config.proxies
  return r

def get_url_json(url, user_agent='desktop', headers=None, retries=3, use_proxy=False):
  r = get_request(url, user_agent, headers, retries, use_proxy)
  if r != None and (r.status_code == 200 or r.status_code == 402):
    try:
      return r.json()
    except:
      logger.warning('error converting response to json from request {}'.format(url))
      write_file(r.text, './debug/json.txt')
  return None

def get_url_html(url, user_agent='desktop', headers=None, retries=3, use_proxy=False):
  r = get_request(url, user_agent, headers, retries, use_proxy)
  if r != None and (r.status_code == 200 or r.status_code == 402):
    return r.text
  return None

def get_url_content(url, user_agent='googlebot', headers=None, retries=3, use_proxy=False):
  r = get_request(url, user_agent, headers, retries, use_proxy)
  if r != None and (r.status_code == 200 or r.status_code == 402):
    return r.content
  return None

def get_redirect_url(url):
  if 'cloudfront.net' in url:
    url_html = get_url_html(url)
    m = re.search(r'"redirect":"([^"]+)"', url_html)
    if m:
      return m.group(1)

  # It would be better to use requests.head because some servers may not support the Range header and the whole file will be downloaded; however, request.get seems to work better for getting redirects
  i = 0
  r = None
  try:
    redirect_url = url
    r = requests.get(url, headers={"Range": "bytes=0-100"}, allow_redirects=False)
    while r.is_redirect and i < 5:
      if not re.search(r'^https?:\/\/', r.headers['location']):
        break
      redirect_url = r.headers['location']
      r = requests.get(redirect_url, headers={"Range": "bytes=0-100"}, allow_redirects=False)
      i += 1
    redirect_url = r.url
  except Exception as e:
    if r:
      status_code = r.status_code
    else:
      status_code = ''
    logger.warning('exception error {}{} getting {}'.format(e.__class__.__name__, status_code, redirect_url))
    return redirect_url

  # Check for a url in the query parameters
  check_query = True
  while check_query:
    check_query = False
    split_url = urlsplit(redirect_url)
    if split_url.query:
      for key, val in parse_qs(split_url.query).items():
        # val[0].startswith('http://') or val[0].startswith('https://')
        if re.search(r'^https?:\/\/', val[0]):
          redirect_url = val[0]
          check_query = True
          break
  return redirect_url

def get_url_title_desc(url):
  html = get_url_html(url)
  if html:
    soup = BeautifulSoup(html, 'html.parser')
    el = soup.find('title')
    if el:
      title = el.get_text()
    else:
      title = url
    el = soup.find('meta', attrs={"name": "description"})
    if el:
      desc = el['content']
    else:
      desc = None
  else:
    title = url
    desc = None
  return title, desc

def post_url(url, data, headers=None):
  try:
    if headers:
      if isinstance(data, dict):
        r = requests.post(url, json=data, headers=headers)
      else:
        r = requests.post(url, data=data, headers=headers)
    else:
      if isinstance(data, dict):
        r = requests.post(url, json=data)
      else:
        r = requests.post(url, data=data)
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
  return lst[min(range(len(lst)), key = lambda i: abs(int(lst[i][k]) - target))]

def image_from_srcset(srcset, target):
  images = []
  for src in srcset.split(','):
    m = re.search(r'^(.+)\s(\d+)', src)
    if m:
      image = {}
      image['src'] = m.group(1)
      image['width'] = int(m.group(2))
      images.append(image)
  if images:
    image = closest_dict(images, 'width', target)
    return image['src']
  return ''

def clean_url(url):
  split_url = urlsplit(url)
  return '{}://{}{}'.format(split_url.scheme, split_url.netloc, split_url.path)

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
  # Also strips \n
  return re.sub(r'^<[^>]+>|<\/[^>]+>$|\n', '', str(soup))

def add_blockquote(text):
  return '<blockquote style="border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;">{}</blockquote>'.format(text)

def open_pullquote():
  return '<blockquote><table><tr><td style="text-align:right; vertical-align:top;"><span style="font-size:2em;">&#x201C;</span></td><td style="padding-top:0.5em;"><em>'

def close_pullquote(author=''):
  end_html = '</em></td><td style="text-align:left; vertical-align:bottom;"><span style="font-size:2em;">&#x201E;</span></td></tr>'
  if author:
    #end_html += '<br /><small>&mdash;&nbsp;{}</small>'.format(author)
    end_html += '<tr><td>&nbsp;</td><td><small>&mdash;&nbsp;{}</small></td><td></td>&nbsp;</tr>'.format(author)
  end_html += '</table></blockquote>'
  return end_html

def add_pullquote(quote, author=''):
  # Strip quotes
  if (quote.startswith('"') or quote.startswith('“') or quote.startswith('‘')) and (quote.endswith('"') or quote.endswith('”') or quote.endswith('’')):
    quote = quote[1:-1]
  pullquote = open_pullquote() + quote + close_pullquote(author)
  return pullquote

def add_image(img_src, caption='', width=None, height=None, link='', img_style='', fig_style='', gawker=False):
  begin_html = '<figure'
  if fig_style:
    begin_html += ' style={}>'.format(fig_style)
  else:
    begin_html += '>'

  if link:
    begin_html += '<a href="{}">'.format(link)

  begin_html += '<img src="{}"'.format(img_src)

  if width:
    begin_html += ' width="{}"'.format(width)
  else:
    begin_html += ' width="100%"'

  if height:
    begin_html += ' height="{}"'.format(height)

  if img_style:
    begin_html += ' style="{}"'.format(img_style)

  begin_html += '/>'

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

def add_video(video_url, video_type, poster='', caption='', width='', height='', img_style='', fig_style='', gawker=False):
  video_src = ''
  if video_type == 'video/mp4' or video_type == 'video/webm':
    video_src = video_url

  elif video_type == 'application/x-mpegURL':
    video_src = '{}/videojs?src={}&type={}&poster={}'.format(config.server, quote_plus(video_url), quote_plus(video_type), quote_plus(poster))

  elif video_type == 'vimeo':
    content = vimeo.get_content(video_url, None, False)
    if content.get('_image'):
      poster = content['_image']
    video_src = '{}/video?url={}'.format(config.server, quote_plus(video_url))
    if not caption:
      caption = '{} | <a href="{}">Watch on Vimeo</a>'.format(content['title'], video_url)

  elif video_type == 'youtube':
    content = youtube.get_content(video_url, None, False)
    if content:
      if content.get('_image'):
        poster = content['_image']
      video_src = '{}/video?url={}'.format(config.server, quote_plus(video_url))
      if not caption:
        caption = '{} | <a href="{}">Watch on YouTube</a>'.format(content['title'], video_url)

  else:
    logger.warning('unknown video type {} for {}'.format(video_type, video_url))
    return ''

  if not video_src:
    return '<p><em>Unable to embed video from <a href="{0}">{0}</a></em></p>'.format(video_url)

  if poster:
    poster = '{}/image?url={}'.format(config.server, quote_plus(poster))
    if width:
      poster += '&width={}'.format(width)
    if height:
      poster += '&height={}'.format(height)
    poster += '&overlay=video'
  else:
    poster = '{}/image?width=1280&height=720&overlay=video'.format(config.server)
    if width:
      poster += '?width={}'.format(width)
    else:
      poster += '?width=1280'
    if height:
      poster += '&height={}'.format(height)
    else:
      poster += '&height=720'
    poster += '&overlay=video'

  return add_image(poster, caption, width, height, video_src, img_style=img_style, fig_style=fig_style, gawker=gawker)

def get_youtube_id(ytstr):
  # ytstr can be either:
  # - 11 digit id only, e.g. D4gPQDyOixQ
  # - watch url, e.g. https://www.youtube.com/watch?v=D4gPQDyOixQ
  # - embed url, e.g. https://www.youtube.com/embed/D4gPQDyOixQ
  # - short url, e.g. https://yout.be/D4gPQDyOixQ
  # - playlist, e.g. https://www.youtube.com/playlist?list=PL0vZL9uwyfOFezIOiBjkdW3TTdn0Q_AKL
  # - embed playlist, e.g. https://www.youtube.com/embed/videoseries?list=PLPDkqknt-rAi5yTQ2-UgtuTvMbV84M9ci
  # - video + playlist, e.g. https://www.youtube.com/watch?v=YxkPuEmIX4U&list=PL0vZL9uwyfOFezIOiBjkdW3TTdn0Q_AKL
  # - also from www.youtube-nocookie.com
  yt_list_id = ''
  if 'list=' in ytstr:
    m = re.search(r'list=([a-zA-Z0-9_-]+)', ytstr)
    if m:
      yt_list_id = m.group(1)
    else:
      logger.warning('unable to determine Youtube playlist id in ' + ytstr)

  yt_video_id = ''
  if '/watch?' in ytstr:
    m = re.search(r'v=([a-zA-Z0-9_-]{11})', ytstr)
  elif '/embed/' in ytstr:
    m = re.search(r'\/embed\/([a-zA-Z0-9_-]{11})', ytstr)
  elif 'youtu.be' in ytstr:
    m = re.search(r'youtu\.be\/([a-zA-Z0-9_-]{11})', ytstr)
  if m:
    yt_video_id = m.group(1)
  else:
    # id only
    if len(ytstr) == 11:
      yt_video_id = ytstr

  if yt_list_id and not yt_video_id:
    yt_html = get_url_html('https://www.youtube.com/embed/videoseries?list={}'.format(yt_list_id))
    if yt_html:
      # Use the first videoId found
      m = re.search(r'"videoId\\":\\"([a-zA-Z0-9_-]{11})\\"', yt_html)
      if m:
        yt_video_id = m.group(1)
  if not yt_video_id:
    logger.warning('unable to determine Youtube video id in ' + ytstr)
  return yt_video_id, yt_list_id

def add_youtube(ytstr, width=None, height=None, caption='', gawker=False):
  yt_video_id, yt_list_id = get_youtube_id(ytstr)
  if not yt_video_id:
    return ''
  return add_embed('https://www.youtube.com/watch?v={}'.format(yt_video_id))

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

def get_twitter_url(tweet_id):
  tweet_json = get_url_json('https://cdn.syndication.twimg.com/tweet?id={}&lang=en'.format(tweet_id))
  if not tweet_json:
    return ''
  return 'https://twitter.com/{}/status/{}'.format(tweet_json['user']['screen_name'], tweet_id)

def add_twitter(tweet_url, tweet_id=''):
  if tweet_url:
    url = tweet_url
  elif tweet_id:
    url = get_twitter_url(tweet_id)
  tweet = twitter.get_content(url, {}, False)
  if not tweet:
    return ''
  return tweet['content_html']

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

def add_instagram(igstr):
  ig = instagram.get_content(igstr, {}, False)
  if not ig:
    return ''
  return ig['content_html']

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

def add_apple_podcast(embed_url, save_debug=True):
  # https://embed.podcasts.apple.com/us/podcast/little-gold-men/id1042433465?itsct=podcast_box_player&itscg=30200&theme=auto
  m = re.search(r'\/id(\d+)', embed_url)
  if not m:
    logger.warning('unable to parse podcast id from ' + embed_url)
    return ''
  json_url = 'https://amp-api.podcasts.apple.com/v1/catalog/us/podcasts/{}?include=episodes'.format(m.group(1))

  s = requests.Session()
  headers = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "en-US,en;q=0.9",
    "access-control-request-headers": "authorization",
    "access-control-request-method": "GET",
    "cache-control": "no-cache",
    "dnt": "1",
    "origin": "https://embed.podcasts.apple.com",
    "pragma": "no-cache",
    "referer": "https://embed.podcasts.apple.com/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "sec-gpc": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36"
  }
  preflight = s.options(json_url, headers=headers)
  if preflight.status_code != 204:
    logger.warning('status code {} getting preflight podcast info from {}'.format(preflight.status_code, embed_url))
    return ''

  headers = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "en-US,en;q=0.9",
    "authorization": "Bearer eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IkRBSlcxUk8wNjIifQ.eyJpc3MiOiJFUk1UQTBBQjZNIiwiaWF0IjoxNjI4NTEwOTQ3LCJleHAiOjE2MzQ3MzE3NDcsIm9yaWdpbiI6WyJodHRwczovL2VtYmVkLnBvZGNhc3RzLmFwcGxlLmNvbSJdfQ.4hpyCflT_5hmcLsD2NpwXMaE9ZhznHcoK0T60XVj7bfeIwibz-fiUao_sH3p8WECcw5f-6v0pFN1VwvSr7klkw",
    "cache-control": "no-cache",
    "dnt": "1",
    "origin": "https://embed.podcasts.apple.com",
    "pragma": "no-cache",
    "referer": "https://embed.podcasts.apple.com/",
    "sec-ch-ua": "\"Chromium\";v=\"92\", \" Not A;Brand\";v=\"99\", \"Google Chrome\";v=\"92\"",
    "sec-ch-ua-mobile": "?0",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "sec-gpc": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36"
  }
  r = s.get(json_url, headers=headers)
  if r.status_code != 200:
    logger.warning('status code {} getting request podcast info from {}'.format(r.status_code, embed_url))
    return ''

  req_json = r.json()
  if save_debug:
    write_file(req_json, './debug/podcast.json')

  podcast_info = req_json['data'][0]['attributes']
  poster = podcast_info['artwork']['url'].replace('{w}', '128').replace('{h}', '128').replace('{f}', 'jpg')
  desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by {}</small>'.format(podcast_info['url'], podcast_info['name'], podcast_info['artistName'])
  podcast_html = '<center><table style="width:360px; border:1px solid black; border-radius:10px; border-spacing:0;"><tr><td style="width:1%; padding:0; margin:0; border-bottom: 1px solid black;"><a href="{}"><img style="display:block; border-top-left-radius:10px;" src="{}" /></a></td><td style="padding-left:0.5em; vertical-align:top; border-bottom: 1px solid black;">{}</td></tr><tr><td colspan="2">Episodes:<ol style="margin-top:0;">'.format(podcast_info['url'], poster, desc)

  for episode in req_json['data'][0]['relationships']['episodes']['data']:
    dt = datetime.fromisoformat(episode['attributes']['releaseDateTime'].replace('Z', '+00:00'))
    date = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    time = []
    t = math.floor(episode['attributes']['durationInMilliseconds'] / 3600000)
    if t >= 1:
      time.append('{} hr'.format(t))
    t = math.ceil((episode['attributes']['durationInMilliseconds'] - 3600000*t) / 60000)
    if t > 0:
      time.append('{} min.'.format(t))
    podcast_html += '<li><a style="text-decoration:none;" href="{}">&#9658;</a>&nbsp;<a href="{}">{}</a> ({}, {})</li>'.format(episode['attributes']['assetUrl'], episode['attributes']['url'], episode['attributes']['name'], date, ' , '.join(time))
  podcast_html += '</ol></td></tr></table></center>'
  return podcast_html

def add_audio_track(track_info):
  desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4>'.format(track_info['url'], track_info['title'])
  if track_info.get('artist'):
    desc += '<small>by {}<br/>'.format(track_info['artist'])
  if track_info.get('album'):
    if track_info.get('artist'):
      desc += '<br/>'
    else:
      desc += '<small>'
    desc += 'from '.format(track_info['album'])
  if track_info.get('artist') or track_info.get('album'):
    desc += '</small>'
  return '<center><table style="width:360px; border:1px solid black; border-radius:10px; border-spacing:0;"><tr><td style="width:1%; padding:0; margin:0;"><a href="{}"><img style="display:block; border-top-left-radius:10px; border-bottom-left-radius:10px;" src="{}" /></a></td><td style="padding-left:0.5em; vertical-align:top;">{}</td></tr></table></center>'.format(track_info['audio_src'], track_info['image'], desc)

def add_embed(url, args={}, save_debug=False):
  embed_args = args.copy()
  embed_args['embed'] = True
  # limit playlists to 10 items
  if re.search(r'(apple|bandcamp|soundcloud|spotify)', url):
    embed_args['max'] = 10

  logger.debug('embed content from ' + url)
  if url.startswith('//'):
    embed_url = 'https:' + url
  else:
    embed_url = url
  if 'cloudfront.net' in url:
    embed_url = get_redirect_url(embed_url)
  module = get_module(embed_url)
  if module:
    content = module.get_content(embed_url, embed_args, save_debug)
    if content:
      return content['content_html']
  return '<blockquote><b>Embedded content from <a href="{0}">{0}</a></b></blockquote>'.format(url)