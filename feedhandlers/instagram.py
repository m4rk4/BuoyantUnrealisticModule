import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit, quote_plus

import config
import utils

import logging
logger = logging.getLogger(__name__)

def format_caption_links(matchobj):
  if matchobj.group(1) == '#':
    return '<a href="https://www.instagram.com/explore/tags/{0}/"> #{0}</a>'.format(matchobj.group(2))
  elif matchobj.group(1) == '@':
    return '<a href="https://www.instagram.com/{0}/">@{0}</a>'.format(matchobj.group(2))

def get_content(url, args, save_debug=False):
  # Need to use a proxy to show images because of CORS
  #imageproxy = 'https://bibliogram.snopyta.org/imageproxy?url='

  # Extract the post id
  m = re.search(r'instagram\.com\/([^\/]+)\/([^\/]+)', url)
  if not m:
    logger.warning('unable to parse instgram url ' + url)
    return None

  ig_url = 'https://www.instagram.com/{}/{}/'.format(m.group(1), m.group(2))
  ig_embed = utils.get_url_html(ig_url + 'embed/captioned/?cr=1')
  if not ig_embed:
    return ''
  if save_debug:
    utils.write_file(ig_embed, './debug/instagram.html')

  soup = BeautifulSoup(ig_embed, 'html.parser')

  el = soup.find(class_='EmbedIsBroken')
  if el:
    msg = el.find(class_='ebmMessage').get_text()
    if 'removed' in msg:
      item = {}
      item['content_html'] = '<blockquote><a href="{}">{}</a></blockquote>'.format(ig_url, msg)
      return item
    else:
      logger.warning('embMessage "{}" in {}'.format(el.get_text(), ig_url))
      return None

  m = re.search(r"window\.__additionalDataLoaded\('extra',(.+)\);<\/script>", ig_embed)
  if m:
    try:
      ig_data = json.loads(m.group(1))
    except:
      ig_data = None

  if ig_data:
    if save_debug:
      utils.write_file(ig_data, './debug/instagram.json')
    avatar = ig_data['shortcode_media']['owner']['profile_pic_url']
    username = ig_data['shortcode_media']['owner']['username']
  else:
    el = soup.find(class_='Avatar')
    avatar = el.img['src']
    username = soup.find(class_='UsernameText').get_text()
  avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, quote_plus(avatar))

  title = '{} posted on Instagram'.format(username)
  caption = None
  post_caption = '<a href="{}"><small>Open in Instagram</small></a>'.format(ig_url)
  if ig_data:
    try:
      caption = ig_data['shortcode_media']['edge_media_to_caption']['edges'][0]['node']['text']
    except:
      caption = None

    if caption:
      caption = caption.replace('\n', '<br />')
      caption = re.sub(r'(@|#)(\w+)', format_caption_links, caption)
      post_caption = '<p>{}</p>'.format(caption) + post_caption

  if not caption:
    caption = soup.find(class_='Caption')
    if caption:
      # Make paragragh instead of div to help with spacing
      caption.name = 'p'
      caption.attrs = {}

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
        title = '{} posted: {}'.format(username, caption.get_text())
        post_caption = str(caption) + post_caption
      while post_caption.startswith('<br/>'):
        post_caption = post_caption[5:]

  post_media = ''
  media_type = soup.find(class_='Embed')['data-media-type']
  if media_type == 'GraphImage':
    for el in soup.find_all('img', class_='EmbeddedMediaImage'):
      if el.has_attr('srcset'):
        img_src = utils.image_from_srcset(el['srcset'], 640)
      else:
        img_src = el['src']
      figure = utils.add_image('{}/image?url={}&width=480'.format(config.server, quote_plus(img_src)), width=480, link=img_src)
      post_media += figure[8:-9]

  elif media_type == 'GraphVideo':
    if ig_data:
      video_src = ig_data['shortcode_media']['video_url']
      img = utils.closest_dict(ig_data['shortcode_media']['display_resources'], 'config_width', 640)
      figure = utils.add_image('{}/image?url={}&width=480&overlay=video'.format(config.server, quote_plus(img['src'])), width=480, link=video_src)
      post_media += figure[8:-9]
    else:
      el = soup.find('img', class_='EmbeddedMediaImage')
      if el:
        poster = '{}/image?url={}&width=480&overlay=video'.format(config.server, quote_plus(el['src']))
        caption = '<a href="{}"><small>Watch on Instagram</small></a>'.format(ig_url)
        figure = utils.add_image(poster, caption, width=480, link=ig_url)
        post_media += figure[8:-9]

  elif media_type == 'GraphSidecar':
    if ig_data:
      for edge in ig_data['shortcode_media']['edge_sidecar_to_children']['edges']:
        if edge['node']['__typename'] == 'GraphImage':
          img_src = edge['node']['display_resources'][0]['src']
          figure = utils.add_image('{}/image?url={}&width=480'.format(config.server, quote_plus(img_src)), width=480, link=img_src)
          post_media += figure[8:-9]

        elif edge['node']['__typename'] == 'GraphVideo':
          video_src = edge['node']['video_url']
          img = utils.closest_dict(edge['node']['display_resources'], 'config_width', 640)
          figure = utils.add_image('{}/image?url={}&width=480&overlay=video'.format(config.server, quote_plus(img['src'])), width=480, link=video_src)
          post_media += figure[8:-9]

        post_media += '<br/><br/>'
      post_media = post_media[:-10]
    else:
      logger.warning('Instagram GraphSidecar media without ig_data in ' + ig_url)

  item = {}
  item['id'] = ig_url
  item['url'] = ig_url
  if len(title) > 50:
    item['title'] = title[:50] + '...'
  else:
    item['title'] = title

  if ig_data and ig_data['shortcode_media'].get('taken_at_timestamp'):
    # Assuming it's UTC
    dt = datetime.fromtimestamp(ig_data['shortcode_media']['taken_at_timestamp']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  item['author'] = {}
  item['author']['name'] = username

  item['content_html'] = '<blockquote style="width:488px; padding:8px 0 8px 8px; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><div style="display:flex; align-items:center;"><img src="{0}"/><span>&nbsp;<a href="https://www.instagram.com/{1}"><b>{1}</b></a></span></div><br/>'.format(avatar, username)

  if post_media:
    item['content_html'] += post_media

  item['content_html'] += '<p>{}</p></blockquote>'.format(post_caption)
  return item

def get_feed(args, save_debug=False):
  return None