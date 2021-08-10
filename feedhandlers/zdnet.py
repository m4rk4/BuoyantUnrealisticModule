import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

from feedhandlers import rss
import utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  split_url = urlsplit(url)
  clean_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, split_url.path)
  article_html = utils.get_url_html(clean_url)
  if not article_html:
    return None
  if save_debug:
    utils.write_file(article_html, './debug/debug.html')

  soup = BeautifulSoup(article_html, 'html.parser')

  for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
    ld_json = json.loads(el.string)
    article_type = ld_json.get('@type')
    if '/video/' in clean_url and article_type == 'VideoObject':
      break
    elif article_type and (article_type == 'NewsArticle' or article_type == 'Review'):
      break
    elif article_type and (article_type == 'Product' and ld_json.get('review')):
      article_type = 'Review'
      ld_json = ld_json['review']
      break

  m = re.search(r'utag_data = ({.*}});', article_html)
  if m:
    utag_data = json.loads(m.group(1))
  else:
    utag_data = None

  item = {}
  if utag_data and utag_data.get('articleId'):
    item['id'] = utag_data['articleId']
  else:
    item['id'] = clean_url
  item['url'] = clean_url

  if article_type == 'VideoObject':
    item['title'] = ld_json['name']

    dt = datetime.fromisoformat(ld_json['uploadDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    item['_image'] = ld_json['thumbnailUrl']
    item['summary'] = ld_json['description']
    item['content_html'] = '<p>{}</p>'.format(ld_json['description'])

    player = soup.find(class_='videoPlayer')
    if player:
      video_options = json.loads(player['data-zdnet-video-options'])
      video = video_options['videos'][0]

      author = ''
      if video.get('author'):
        if video['author'].get('firstName') or video['author'].get('lastName'):
          author = '{} {}'.format(video['author']['firstName'], video['author']['lastName'])
      if video.get('moreAuthors'):
        for a in video['moreAuthors']:
          if a.get('firstName') or a.get('lastName'):
            author += ', {} {}'.format(a['firstName'], a['lastName'])
      if author:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', author)

      if 'mp4' in video:
        item['content_html'] = utils.add_video(video['mp4'], 'video/mp4', video['previewImg']) + item['content_html']
      elif 'm3u8' in video:
        item['content_html'] = utils.add_video(video['m3u8'], 'application/x-mpegURL', video['previewImg']) + item['content_html']
  elif article_type == 'NewsArticle' or article_type == 'Review':
    item['title'] = ld_json['headline']
    dt = datetime.fromisoformat(ld_json['datePublished']).astimezone(tz=None)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt_pub.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    dt = datetime.fromisoformat(ld_json['dateModified']).astimezone(tz=None)
    item['date_modified'] = dt.isoformat()

    c = ''
    author = ''
    for a in ld_json['author']:
      author += c + a['name']
      c = ', '
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', author)
    if utag_data:
      item['tags'] = utag_data['topicName'].copy()

    if ld_json.get('thumbnailUrl'):
      item['_image'] = ld_json['thumbnailUrl']
    else:
      # Use first image from gallery
      el = soup.find(class_='reviewGallery')
      if el:
        img = el.find('img')
        if img:
          if img.get('data-original'):
            item['_image'] = img['data-original']
          elif img.get('src'):
            item['_image'] = img['src']

    item['summary'] = ld_json['description']

    item['content_html'] = ''
    if '/pictures/' in clean_url:
      gallery = soup.find(class_='photoGallery')
      for el in gallery.find_all('li', class_='image'):
        img = el.find('img')
        if img.get('data-src'):
          img_src = img['data-src']
        else:
          img_src = img['src']
        details = el.find(class_='details')
        item['content_html'] += utils.add_image(img_src) + str(details)
    else:
      article_body = soup.find(class_='storyBody')

      for el in article_body.find_all('script'):
        el.decompose()

      for el in article_body.find_all(class_=re.compile(r'listicle-precap|relatedContent|relatedReviews|sharethrough', flags=re.I)):
        el.decompose()

      for el in article_body.find_all('figure', class_='image'):
        img = el.find('img')
        if 'lazy' in img['class']:
          img_src = img['data-original']
        else:
          img_src = img['src']
        img_caption = ''
        caption = el.find(class_='caption')
        credit = el.find(class_='credit')
        if caption:
          img_caption = caption.get_text()
        if credit:
          if img_caption:
            img_caption += ' '
          img_caption += '(Credit: {})'.format(credit.get_text().strip())
        new_el = BeautifulSoup(utils.add_image(img_src, img_caption), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

      for el in article_body.find_all(class_='shortcodeGalleryWrapper'):
        gallery = ''
        for it in el.find_all('img', class_="lazy"):
          name = it['data-original'].split('/')[-1]
          img = soup.find('img', attrs={"alt": "{}".format(name)})
          if img:
            if img.get('data-original'):
              gallery += utils.add_image(img['data-original'])
            elif img.get('src'):
              gallery += utils.add_image(img['src'])
        if gallery:
          new_el = BeautifulSoup('<h3>Gallery</h3>' + gallery, 'html.parser')
          el.insert_after(new_el)
        el.decompose()

      for el in article_body.find_all(class_='video'):
        player = el.find(class_='videoPlayer')
        if player:
          new_el = None
          video_options = json.loads(player['data-zdnet-video-options'])
          if 'mp4' in video_options['videos'][0]:
            new_el = BeautifulSoup(utils.add_video(video_options['videos'][0]['mp4'], 'video/mp4', video_options['videos'][0]['previewImg']), 'html.parser')
          elif 'm3u8' in video_options['videos'][0]:
            new_el = BeautifulSoup(utils.add_video(video_options['videos'][0]['m3u8'], 'application/x-mpegURL', video_options['videos'][0]['previewImg']), 'html.parser')
          if new_el:
            el.insert_after(new_el)
            el.decompose()

      for el in article_body.find_all(class_='shortcode'):
        if 'media-source' in el['class']:
          it = el.find('iframe')
          if it and it.get('id') and 'iframe_youtube' in it['id']:
            print(it)
            new_el = BeautifulSoup(utils.add_video(it['data-src'], 'youtube'), 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        elif not 'listicle' in el['class']:
          logger.warning('unhandled shortcode class {} in {}'.format(el['class'], url))

      # Review Pros/Cons
      for el in article_body.find_all(class_='row'):
        pros = el.find('ul', class_='pros')
        cons = el.find('ul', class_='cons')
        if pros and cons:
          cons['style'] = 'list-style-type: none;'
          el.insert_after(cons)
          el.insert_after(BeautifulSoup('<h3>Cons</h3>', 'html.parser'))
          pros['style'] = 'list-style-type: none;'
          el.insert_after(pros)
          el.insert_after(BeautifulSoup('<h3>Pros</h3>', 'html.parser'))
          el.decompose()

      for el in article_body.find_all(class_='listicle'):
        new_listicle = ''
        for it in el.find_all(True, recursive=False):
          if it.name == 'h2' or it.name == 'h3':
            new_listicle += '<{0}>{1}</{0}>'.format(it.name, it.get_text().strip())
          elif it.name == 'a' or (it.get('class') and 'imageContainer' in it.get('class')):
            img = it.find('img')
            if img:
              if 'lazy' in img['class']:
                img_src = img['data-original']
              else:
                img_src = img['src']
              new_listicle += utils.add_image(img_src)
            else:
              new_listicle += '<a href="{}">{}</a><br />'.format(utils.clean_referral_link(it['href']), it.get_text().strip())
          else:
            new_listicle += str(it)
        el.insert_after(BeautifulSoup(new_listicle, 'html.parser'))
        el.decompose()

      for el in article_body.find_all(['p','h3']):
        try:
          if el.strong and re.search(r'^(Also:|Must read:|SEE:)', el.strong.get_text()):
            el.decompose()
          elif el.strong and re.search(r'^(RECENT AND RELATED CONTENT)', el.strong.string):
            while ((el.next_sibling.a and el.next_sibling.a.strong) or (el.next_sibling.strong and el.next_sibling.strong.a)):
              el.next_sibling.decompose()
            el.decompose()
          elif re.search(r'^(Related Stories|Related Coverage|Read more reviews)', el.get_text(), flags=re.I):
            if el.next_sibling.name == 'ul':
              el.next_sibling.decompose()
              el.decompose()
        except Exception as e:
          logger.warning('zdnet exception: ' + str(e))
          pass

      # Add a lead image if one is not present
      if article_body.contents[1].name != 'figure':
        if item.get('_image'):
          item['content_html'] = utils.add_image(item['_image']) + item['content_html']

      item['content_html'] += str(article_body)
  
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)