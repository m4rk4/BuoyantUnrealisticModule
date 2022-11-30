import asyncio, importlib, io, json, math, os, pytz, random, re, requests, string, tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from PIL import ImageFile
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from urllib.parse import parse_qs, quote_plus, urlsplit

import config
import utils
from feedhandlers import instagram, twitter, vimeo, youtube

import logging
logger = logging.getLogger(__name__)


def get_site_json(url):
  tld = tldextract.extract(url.strip())
  if tld.domain == 'youtu' and tld.suffix == 'be':
    domain = 'youtu.be'
  elif tld.domain == 'megaphone' and tld.suffix == 'fm':
    domain = 'megaphone.fm'
  elif tld.domain == 'go':
    domain = tld.subdomain
  elif tld.domain == 'feedburner':
    domain = urlsplit(url).path.split('/')[1].lower()
  else:
    domain = tld.domain
  sites_json = read_json_file('./sites.json')
  if sites_json.get(domain):
    site_json = sites_json[domain]
  elif domain in sites_json['wp-posts']['sites']:
    site_json = {
        "module": "wp_posts",
        "wpjson_path": "/wp-json",
        "posts_path": "/wp/v2/posts"
    }
  else:
    site_json = None
  return site_json

def get_module(url, handler=''):
  module = None
  module_name = ''
  if handler:
    module_name = '.{}'.format(handler)
  elif url:
    if 'wp-json' in url:
      module_name = '.wp_posts'
    else:
      site_json = get_site_json(url)
      if site_json:
        module_name = '.{}'.format(site_json['module'])
  if not module_name:
    split_url = urlsplit(url)
    if url_exists('{}://{}/wp-json/wp/v2/posts'.format(split_url.scheme, split_url.netloc)):
      module_name = '.wp_posts'
    else:
      dt = datetime.utcnow().date()
      gannet_url = '{}://{}/sitemap/{}'.format(split_url.scheme, split_url.netloc, dt.strftime('%Y/%B/%d/'))
      if url_exists(gannet_url.lower()):
        module_name = '.gannett'
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
def requests_retry_session(retries=4):
  session = requests.Session()
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

def get_request(url, user_agent, headers=None, retries=3, allow_redirects=True):
  # https://www.whatismybrowser.com/guides/the-latest-user-agent/
  if user_agent == 'desktop':
    ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36'
  elif user_agent == 'mobile':
    ua = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Mobile/15E148 Safari/604.1'
  elif user_agent == 'googlebot':
    # https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers
    ua = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
  else: # Googlebot
    ua = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'

  if headers:
    if not (headers.get('user-agent') or headers.get('User-Agent') or headers.get('sec-ch-ua')):
      headers['user-agent'] = ua
  else:
    headers = {}
    headers['user-agent'] = ua

  r = None
  try:
    r = requests_retry_session(retries).get(url, headers=headers, timeout=10, allow_redirects=allow_redirects)
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
  return r

def get_browser_request(url, get_json=False, save_screenshot=False):
  with sync_playwright() as playwright:
    webkit = playwright.webkit
    dev = playwright.devices['iPhone 13']
    browser = webkit.launch()
    context = browser.new_context(**dev)
    page = context.new_page()
    try:
      r = page.goto(url)
      if get_json:
        content = r.json()
      else:
        content = r.text()
      if save_screenshot:
        page.screenshot(path="./debug/screenshot.png")
    except PlaywrightTimeoutError:
      logger.warning('timeout error getting ' + url)
      content = None
    browser.close()
    return content

def get_url_json(url, user_agent='desktop', headers=None, retries=3, allow_redirects=True, use_browser=False):
  site_json = get_site_json(url)
  if use_browser or (site_json and site_json.get('use_browser')):
    return get_browser_request(url, get_json=True)

  r = get_request(url, user_agent, headers, retries, allow_redirects)
  if r != None and (r.status_code == 200 or r.status_code == 402 or r.status_code == 404):
    try:
      return r.json()
    except:
      logger.warning('error converting response to json from request {}'.format(url))
      write_file(r.text, './debug/json.txt')
  return None

def get_url_html(url, user_agent='desktop', headers=None, retries=3, allow_redirects=True, use_browser=False):
  site_json = get_site_json(url)
  if use_browser or (site_json and site_json.get('use_browser')):
    return get_browser_request(url)

  r = get_request(url, user_agent, headers, retries, allow_redirects)
  if r != None and (r.status_code == 200 or r.status_code == 402):
    return r.text
  return None

def get_url_content(url, user_agent='googlebot', headers=None, retries=3, allow_redirects=True, use_browser=False):
  site_json = get_site_json(url)
  if use_browser or (site_json and site_json.get('use_browser')):
    return get_browser_request(url)

  r = get_request(url, user_agent, headers, retries, allow_redirects)
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
    r = requests.get(url, headers={"Range": "bytes=0-100"}, allow_redirects=False, timeout=5)
    while r.is_redirect and i < 5:
      if not re.search(r'^https?:\/\/', r.headers['location']):
        break
      redirect_url = r.headers['location']
      r = requests.get(redirect_url, headers={"Range": "bytes=0-100"}, allow_redirects=False, timeout=5)
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
      if redirect_url.startswith('https://www.amazon.com/'):
        redirect_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, split_url.path)
      else:
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

def post_url(url, data=None, json_data=None, headers=None):
  try:
    if data:
      if headers:
        r = requests.post(url, data=data, headers=headers)
      else:
        r = requests.post(url, data=data)
    elif json_data:
      if headers:
        r = requests.post(url, json=json_data, headers=headers)
      else:
        r = requests.post(url, json=json_data)
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

def get_or_create_event_loop():
  try:
    return asyncio.get_event_loop()
  except RuntimeError as ex:
    if "There is no current event loop in thread" in str(ex):
      loop = asyncio.new_event_loop()
      asyncio.set_event_loop(loop)
      return asyncio.get_event_loop()

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

def read_file(filename):
  content = ''
  if os.stat(filename).st_size > 0:
    f = io.open(filename, mode="r", encoding="utf-8")
    content = f.read()
  else:
    logger.warning('empty file {}'.format(filename))
  return content

def closest_value(lst, target):
  return lst[min(range(len(lst)), key = lambda i: abs(int(lst[i]) - target))]

def closest_dict(lst, k, target):
  return lst[min(range(len(lst)), key = lambda i: abs(int(lst[i][k]) - target))]

def image_from_srcset(srcset, target):
  images = []
  for m in re.findall(r'(http\S+) (\d+)w', srcset):
      image = {}
      image['src'] = m[0]
      image['width'] = int(m[1])
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

def format_display_date(dt_utc, include_time=True):
  dt_loc = dt_utc.astimezone(pytz.timezone(config.local_tz))
  if include_time:
    return '{}. {}, {}, {}:{} {} EST'.format(dt_loc.strftime('%b'), dt_loc.day, dt_loc.year, int(dt_loc.strftime('%I')), dt_loc.strftime('%M'), dt_loc.strftime('%p').lower())
  else:
    return '{}. {}, {}'.format(dt_loc.strftime('%b'), dt_loc.day, dt_loc.year)

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

def add_blockquote(quote, pullquote_check=True):
  if quote.startswith('<p>'):
    quote = quote.replace('<p>', '')
    quote = quote.replace('</p>', '<br/><br/>')
    if quote.endswith('<br/><br/>'):
      quote = quote[:-10]
  if pullquote_check:
    m = re.search(r'^["“‘]([^"“‘"”’]+)["”’]$', quote)
    if m:
      return add_pullquote(quote)
  return '<blockquote style="border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;">{}</blockquote>'.format(quote)

def open_pullquote():
  return '<table style="margin-left:10px; margin-right:10px;"><tr><td style="font-size:3em; vertical-align:top;">&#8220;</td><td style="vertical-align:top; padding-top:1em;"><em>'

def close_pullquote(author=''):
  end_html = '</em>'
  if author:
    end_html += '<br/><small>&mdash;&nbsp;{}</small>'.format(author)
  end_html += '</td></tr></table>'
  return end_html

def add_pullquote(quote, author=''):
  if quote.startswith('<p>'):
    quote = quote.replace('<p>', '')
    quote = quote.replace('</p>', '<br/><br/>')
    if quote.endswith('<br/><br/>'):
      quote = quote[:-10]
  # Strip quotes
  quote = quote.strip()
  if (quote.startswith('"') or quote.startswith('“') or quote.startswith('‘')) and (quote.endswith('"') or quote.endswith('”') or quote.endswith('’')):
    quote = quote[1:-1]
  pullquote = open_pullquote() + quote + close_pullquote(author)
  return pullquote

def get_image_size(img_src):
  r = requests.get(img_src, headers={"Range": "bytes=0-1024"})
  if r.status_code == 200 or r.status_code == 206:
    try:
      p = ImageFile.Parser()
      p.feed(r.content)
      if not p.image:
        r = requests.get(img_src)
        if r.status_code == 200 or r.status_code == 206:
          p = ImageFile.Parser()
          p.feed(r.content)
      if p.image:
        return p.image.size[0], p.image.size[1]
    except:
      logger.debug('invalid')
      pass
  return None, None

def add_image(img_src, caption='', width=None, height=None, link='', img_style='', fig_style='', heading='', desc=''):
  fig_html = '<figure '
  if fig_style:
    fig_html += 'style="{}">'.format(fig_style)
  else:
    fig_html += 'style="margin:0; padding:0;">'

  if heading:
    fig_html += '<div style="text-align:center; font-size:1.1em; font-weight:bold">{}</div>'.format(heading)

  if link:
    fig_html += '<a href="{}">'.format(link)

  fig_html += '<img src="{}" loading="lazy" style="display:block; margin-left:auto; margin-right:auto;'.format(img_src)
  if width:
    fig_html += ' width:{};'.format(width)
  else:
    fig_html += ' width:100%;'
  if height:
    fig_html += ' height:{};'.format(height)
  if img_style:
    fig_html += ' {}'.format(img_style)
  fig_html += '"/>'

  if link:
    fig_html += '</a>'

  if caption:
    fig_html += '<figcaption><small>{}</small></figcaption>'.format(caption)

  if desc:
    fig_html += desc

  fig_html += '</figure>'
  return fig_html

def add_audio(audio_src, title='', poster='', desc='', link=''):
  if not poster:
    if not title:
      title = 'Play'
    audio_html = '<blockquote><h4><a style="text-decoration:none;" href="{0}">&#9654;</a>&nbsp;<a href="{0}">{1}</a></h4>{2}</blockquote>'.format(audio_src, title, desc)
  return audio_html

def add_video(video_url, video_type, poster='', caption='', width=1280, height='', img_style='', fig_style=''):
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
      #video_src = '{}/video?url={}'.format(config.server, quote_plus(video_url))
      video_src = video_url
      if not caption:
        caption = '{} | <a href="{}">Watch on YouTube</a>'.format(content['title'], video_url)

  else:
    logger.warning('unknown video type {} for {}'.format(video_type, video_url))
    return ''

  if not video_src:
    return '<p><em>Unable to embed video from <a href="{0}">{0}</a></em></p>'.format(video_url)

  if poster:
    poster = '{}/image?url={}&width={}'.format(config.server, quote_plus(poster), width)
    if height:
      poster += '&height={}'.format(height)
    poster += '&overlay=video'
  elif video_type == 'video/mp4':
    poster = '{}/image?url={}&width={}&overlay=video'.format(config.server, quote_plus(video_src), width)
  else:
    poster = '{}/image?width={}'.format(config.server, width)
    if height:
      poster += '&height={}'.format(height)
    else:
      poster += '&height=720'
    poster += '&overlay=video'

  return add_image(poster, caption, '', '', video_src, img_style=img_style, fig_style=fig_style)

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

  m = None
  yt_video_id = ''
  if '/watch?' in ytstr:
    m = re.search(r'v=([a-zA-Z0-9_-]{11})', ytstr)
  elif '/embed/' in ytstr:
    m = re.search(r'\/embed\/([a-zA-Z0-9_-]{11})', ytstr)
  elif 'youtu.be' in ytstr:
    m = re.search(r'youtu\.be\/([a-zA-Z0-9_-]{11})', ytstr)
  if m and m.group(1) != 'videoseries':
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

def add_youtube(ytstr, width=None, height=None, caption=''):
  yt_video_id, yt_list_id = get_youtube_id(ytstr)
  if not yt_video_id:
    return ''
  return add_embed('https://www.youtube.com/watch?v={}'.format(yt_video_id))

def add_youtube_playlist(yt_id, width=640, height=360):
  return '<center><iframe width="{}" height="{}"  src="https://www.youtube-nocookie.com/embed/videoseries?list={}" allow="encrypted-media" allowfullscreen></iframe></center>'.format(width, height, yt_id)

def get_twitter_url(tweet_id):
  # tweet_json = get_url_json('https://cdn.syndication.twimg.com/tweet?id={}&lang=en'.format(tweet_id))
  tweet_json = utils.get_url_json('https://cdn.syndication.twimg.com/tweet-result?id={}&lang=en'.format(tweet_id))
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

def add_instagram(igstr):
  ig = instagram.get_content(igstr, {}, False)
  if not ig:
    return ''
  return ig['content_html']

def add_bar(label, value, max_value, show_percent=True):
  pct = 100*value/max_value
  if show_percent:
    val = '{:.1f}%'.format(pct)
  else:
    val = value
  return '<div style="width:{}%; background-color:lightgrey; margin:10px 0 10px 0;">{}<span style="float:right;">{}</span><span style="clear:right;"></span></div>'.format(round(pct), label, val)

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
  embed_url = url
  if url.startswith('//'):
    embed_url = 'https:' + url

  if 'twitter.com' in embed_url:
    embed_url = clean_url(embed_url)
  elif 'youtube.com/embed' in embed_url:
    if 'list=' not in embed_url:
      embed_url = clean_url(embed_url)
  elif 'cloudfront.net' in embed_url:
    embed_url = get_redirect_url(embed_url)
  elif 'embedly.com' in embed_url:
    split_url = urlsplit(embed_url)
    params = parse_qs(split_url.query)
    if params.get('src'):
      embed_url = params['src'][0]
  elif 'cdn.iframe.ly' in embed_url:
    embed_html = utils.get_url_html(embed_url)
    if embed_html:
      m = re.search(r'"linkUri":"([^"]+)"', embed_html)
      if m:
        embed_url = m.group(1)
  logger.debug('embed content from ' + embed_url)

  embed_args = args.copy()
  embed_args['embed'] = True
  # limit playlists to 10 items
  if re.search(r'(apple|bandcamp|soundcloud|spotify)', embed_url):
    embed_args['max'] = 10

  module = get_module(embed_url)
  if module:
    content = module.get_content(embed_url, embed_args, save_debug)
    if content:
      return content['content_html']

  page_html = get_url_html(embed_url)
  if page_html:
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('meta', attrs={"property": "og:image"})
    if el:
      img_src = el['content']
      el = soup.find('meta', attrs={"property": "og:title"})
      if el:
        title = el['content'].strip()
      else:
        el = soup.find('title')
        if el:
          title = el.get_text().strip()
        else:
          title = embed_url
      embed_html = '<table><tr><td style="width:128px;"><a href="{0}"><img src="{1}" style="width:128px;"/></a></td><td><div style="font-size:1.2em; font-weight:bold;"><a href="{0}">{2}</a></div><small>{3}</small></td></tr></table>'.format(embed_url, img_src, title, urlsplit(embed_url).netloc)
      return embed_html

  return '<blockquote><b>Embedded content from <a href="{0}">{0}</a></b></blockquote>'.format(embed_url)

def get_content(url, args, save_debug=False):
  content = None
  module = get_module(url)
  if module:
    content = module.get_content(url, args, save_debug)
  return content