import json, pytz, re
from datetime import datetime
from urllib.parse import urlsplit
from bs4 import BeautifulSoup

from feedhandlers import rss
import utils

import logging
logger = logging.getLogger(__name__)

def get_image_src(id, format, width):
  if format == 'gif':
    return 'https://i.kinja-img.com/gawker-media/image/upload/c_scale,fl_progressive,q_80,w_{}/{}.gif'.format(width, id)
  return 'https://i.kinja-img.com/gawker-media/image/upload/c_fill,f_auto,fl_progressive,g_center,pg_1,q_80,w_1000/{}.{}'.format(id, format)

def get_kinja_video(video_id, url):
  video_src = ''
  video_json = utils.get_url_json('https://kinja.com/api/core/video/views/videoById?videoId={}'.format(video_id))
  if video_json:
    video_src = video_json['data']['fastlyUrl']
    width = video_json['data']['poster'].get('width')
    if not width:
      width = 640
    poster = get_image_src(video_json['data']['poster']['id'], video_json['data']['poster']['format'], width)
  else:
    # Try to extract the video src from the page
    url_html = utils.get_url_html(url)
    soup = BeautifulSoup(url_html, 'html.parser')
    el = soup.find('script', attrs={"type": "application/ld+json"})
    if el:
      ld_json = json.loads(el.string)
      if ld_json:
        for video in ld_json['video']:
          if video_id in video['contentUrl']:
            video_src = video['contentUrl']
            poster = video['thumbnailUrl'][0]
            break

  if not video_src:
    logger.warning('unable to get KinjaVideo source for id {} in {}'.format(video_id, url))
    return ''

  if 'm3u8' in video_src:
    video_type = 'application/x-mpegURL'
  elif 'mp4' in video['contentUrl']:
    video_type = 'video/mp4'
  else:
    logger.warning('unknown video type in for {} in {}'.format(video_src, url))
    video_type = 'application/x-mpegURL'

  return utils.add_video(video_src, video_type, poster)

def get_content(url, args, save_debug=False):
  item = {}
  split_url = urlsplit(url)
  m = re.search(r'-(\d+)$', split_url.path)
  if not m:
    logger.warning('unable to parse article id in {}'.format(url))
  article_json_url = 'https://{}/api/core/corepost/getList?id={}'.format(split_url.netloc, m.group(1))
  article_json = utils.get_url_json(article_json_url)
  if article_json is None:
    return None

  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(article_json, file, indent=4)

  article_data = article_json['data'][0]

  item['id'] = article_data['id']
  item['url'] = article_data['permalink']
  # Remove html tags
  item['title'] = BeautifulSoup(article_data['headline'], 'html.parser').text

  tz = pytz.timezone(article_data['timezone'])
  dt = datetime.fromtimestamp(article_data['publishTimeMillis']/1000)
  dt_pub = tz.localize(dt).astimezone(pytz.utc)
  item['date_published'] = dt_pub.isoformat()
  item['_timestamp'] = dt_pub.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt_pub.strftime('%b'), dt_pub.day, dt_pub.year)

  dt = datetime.fromtimestamp(article_data['lastUpdateTimeMillis']/1000)
  dt_mod = tz.localize(dt).astimezone(pytz.utc)
  item['date_modified'] = dt_mod.isoformat()

  if article_data.get('authorIds'):
    author_json_url = 'https://{}/api/profile/users?'.format(split_url.netloc)
    for author_id in article_data['authorIds']:
      author_json_url += 'ids={}&'.format(author_id)
    author_json_url = author_json_url[:-1]
    author_json = utils.get_url_json(author_json_url)
    if author_json:
      authors = []
      for author in author_json['data']:
        authors.append(author['displayName'])
      if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  if article_data.get('tags'):
    item['tags'] = []
    for tag in article_data['tags']:
      item['tags'].append(tag['displayName'])

  if article_data.get('sharingMainImage'):
    item['_image'] = get_image_src(article_data['sharingMainImage']['id'], article_data['sharingMainImage']['format'], article_data['sharingMainImage']['width'])

  item['summary'] = article_data['plaintext']

  body_html = ''
  container_break = False

  def iter_body(body_json):
    nonlocal url
    nonlocal body_html
    nonlocal container_break

    img_src_root = 'https://i.kinja-img.com/gawker-media/image/upload/c_fill,f_auto,fl_progressive,g_center,pg_1,q_80,'
    img_size = 'w_800'

    for it in body_json:
      if it['type'] == 'Paragraph':
        tag = '<p>'
        endtag = '</p>'
        for container in it['containers']:
          if container['type'] == 'List':
            if container['style'] == 'Bullet':
              list_tag = 'ul'
            else:
              list_tag = 'ol'
            if body_html.endswith('</{}></p>'.format(list_tag)):
              body_html = body_html[:-9]
              tag = '<li>'
            else:
              tag = '<p><{}><li>'.format(list_tag)
            endtag = '</li></{}></p>'.format(list_tag)

          elif container['type'] == 'BlockQuote':
            if body_html.endswith('</blockquote>') and not container_break:
              body_html = body_html[:-13]
              tag = '<p>'
            else:
              tag = '<blockquote style="border-left: 3px solid #ccc; margin: 1em 1em; padding: 0 0.5em;"><p>'
            endtag = '</p></blockquote>'

          else:
            logger.warning('unhandled container {} in {}'.format(container['type'], article_json_url))
        body_html += tag
        iter_body(it['value'])
        body_html += endtag
        container_break = False

      elif it['type'] == 'Text':
        tag = ''
        endtag = ''
        if 'Bold' in it['styles']:
          tag += '<b>'
          endtag = '</b>' + endtag
        if 'Italic' in it['styles']:
          tag += '<i>'
          endtag = '</i>' + endtag
        if 'Underline' in it['styles']:
          tag += '<u>'
          endtag = '</u>' + endtag
        body_html += '{}{}{}'.format(tag, it['value'], endtag)

      elif it['type'] == 'Link':
        body_html += '<a href="{}">'.format(it['reference'])
        iter_body(it['value'])
        body_html += '</a>'

      elif it['type'] == 'LinkPreview' and it['style'] != 'CommerceCondensed':
        link_html = utils.get_url_html(it['url'])
        if link_html:
          soup = BeautifulSoup(link_html, 'html.parser')
          title = soup.title.string
          meta = soup.find('meta', attrs={"name": "description"})
          if meta:
            desc = ' &ndash; <i>{}</i>'.format(meta['content'])
          else:
            desc = ''
        else:
          title = it['url']
          desc = ''
        body_html += '<p style="margin-right: 10%; margin-left: 10%; padding: .5em; font-size: .8em; border: solid 1px; border-radius: 4px;">Related: <a href="{}">{}</a>{}</p>'.format(it['url'], title, desc)

      elif it['type'] == 'LineBreak':
        body_html += '<br />'

      elif it['type'] == 'PageBreak' or it['type'] == 'HorizontalRule':
        body_html += '<hr style="width:80%;"/>'

      elif it['type'] == 'Header':
        tag = 'h{}'.format(it['level'])
        body_html += '<{}>'.format(tag)
        iter_body(it['value'])
        body_html += '</{}>'.format(tag)

      elif it['type'] == 'PullQuote':
        body_html += utils.open_pullquote()
        iter_body(it['value'])
        if body_html.endswith('\u201d'):
          # Remove the quotes
          body_html = re.sub(r'\u201c(?![\s\S]*\u201c)', '', body_html)
          body_html = re.sub(r'\u201d(?![\s\S]*\u201d)', '', body_html)
        body_html += utils.close_pullquote()

      elif it['type'] == 'Quotable':
        body_html += '<table><tr><td width="120px" align="center"><img style="border-radius: 50%;" src="{}w_80,h_80/{}.{}" /></td><td><h4>'.format(img_src_root, it['image']['id'], it['image']['format'])
        iter_body(it['header'])
        body_html += '</h4><p>'
        iter_body(it['content'])
        body_html += '</p></td></tr></table>'

      elif it['type'] == 'ReviewBox':
        body_html += '<div style="background-color: #ccc ; margin: 0 10vh; padding: 0.5em 1em; border: none;">'
        for text in it['text']:
          body_html += '<p><b>{}</b><br />{}</p>'.format(text['label'].upper(), text['value'])
        body_html += '</div>'

      elif re.search(r'Image|Slideshow|FullBleedWidget', it['type'], flags=re.I):
        if it['type'] == 'Slideshow':
          images = it['slides']
          n_images = len(it['slides'])
        else:
          n_images = 1

        n = 1
        for n in range(n_images):
          if it['type'] == 'Image':
            image = it
          elif it['type'] == 'Slideshow':
            image = it['slides'][n]
          elif it['type'] == 'FullBleedWidget':
            image = it['image']

          if 'overlay' in it:
            img_src = get_image_src(it['overlay']['id'], it['overlay']['format'], it['overlay']['width'])
            bg_src = get_image_src(image['id'], image['format'], image['width'])
          else:
            img_src = get_image_src(image['id'], image['format'], image['width'])
            bg_src = ''
          begin_html, end_html = utils.add_image(img_src, background=bg_src, gawker=True)
          body_html += begin_html

          caption = None
          attribution = None
          begin_caption = '<figcaption><small>'
          end_caption = '</small></figcaption>'
          has_caption = False

          if it['type'] == 'Image' or it['type'] == 'Slideshow':
            if image.get('caption'):
              caption = image['caption']
            if image.get('attribution'):
              attribution = image['attribution']
          else: # FullBleedWidget
            if it.get('caption'):
              caption = it['caption']
            if it.get('attribution'):
              attribution = it['attribution']
          if n_images > 1:
            has_caption = True
            body_html += '{}[{}/{}] '.format(begin_caption, n+1, n_images)
          if caption:
            if not has_caption:
              has_caption = True
              body_html += begin_caption
            iter_body(caption)
          if attribution:
            if has_caption:
              body_html += ' | '
            else:
              has_caption = True
              body_html += begin_caption
            body_html += '{}: '.format(attribution[0]['label'])
            iter_body(attribution[0]['credit'])
            if attribution[0].get('source'):
              body_html += ' ('
              iter_body(attribution[0]['source'])
              body_html += ')'
          if has_caption:
            body_html += end_caption
          body_html += end_html

      elif it['type'] == 'YoutubeVideo' or it['type'] == 'YoutubePlaylist':
        print(it['id'])
        if it['type'] == 'YoutubeVideo':
          yt_url = 'https://www.youtube-nocookie.com/embed/' + it['id']
        else: # YoutubePlaylist
          yt_url = 'https://www.youtube-nocookie.com/embed/' + it['initialVideo']
        begin_html, end_html = utils.add_video(yt_url, 'youtube', gawker=True)
        body_html += begin_html
        if it.get('caption'):
          iter_body(it['caption'])
          body_html += ' | '
        if it['type'] == 'YoutubePlaylist':
          body_html += '<a href="https://www.youtube-nocookie.com/embed/videoseries?list={}">YouTube Playlist</a> | '.format(it['id'])
        body_html += end_html

      elif it['type'] == 'Vimeo':
        body_html += utils.add_vimeo(it['id'])

      elif it['type'] == 'KinjaVideo':
        body_html += get_kinja_video(it['id'], url)

      elif it['type'] == 'Twitter':
        tweet = utils.add_twitter(it['id'])
        if tweet:
          body_html += tweet
        else:
          logger.warning('unable to add tweet {} in {}'.format(it['id'], url))

      elif it['type'] == 'TikTok':
        body_html += utils.add_tiktok(it['id'])

      elif it['type'] == 'Instagram':
        body_html += utils.add_instagram('https://www.instagram.com/p/' + it['id'])

      elif it['type'] == 'Iframe':
        if 'youtube.com' in it['source']:
          body_html += utils.add_video(it['source'], 'youtube')
        else:
          width = str(it['width']['value'])
          if it['width']['unit'] == 'Percent':
            width += '%'
          height = str(it['height']['value'])
          if it['height']['unit'] == 'Percent':
            height += '%'
          body_html += '<iframe width="{}" height="{}" style="border:none;" src="{}"></iframe>'.format(width, height, it['source'])

      elif it['type'] == 'ReplyInset':
        m = re.search(r'\/(\d+)$', it['url'])
        if m:
          body_html += '<iframe width="640" height="628" scrolling="no" style="border:none;" src="https://api.kinja.com/embed/thread/{}"></iframe>'.format(m.group(1))

      elif it['type'] == 'ContainerBreak':
        container_break = True

      elif it['type'] == 'CommerceInset' or it['type'] == 'LinkPreview':
        # Skip
        pass

      else:
        logger.warning('unhandled {} in {}'.format(it['type'], article_json_url))
    return

  if article_data.get('featuredMedia'):
    featured_media = []
    featured_media.append(article_data['featuredMedia'])
    iter_body(featured_media)

  iter_body(article_json['data'][0]['body'])

  item['content_html'] = body_html

  if 'removeimage' in args:
    del item['image']
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)