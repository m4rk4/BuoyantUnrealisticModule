import json, re
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

from feedhandlers import apple, bandcamp, rss, soundcloud, spotify, wp_posts
import utils

import logging
logger = logging.getLogger(__name__)

def find_elements(el_name, el_json, el_ret):
  for i in range(0, len(el_json)):
    if isinstance(el_json[i], str):
      if el_json[i] == el_name:
        el_ret.append(el_json)
    elif isinstance(el_json[i], list):
      find_elements(el_name, el_json[i], el_ret)
  return

def get_content(url, args, save_debug=False):
  if re.search(r'wired\.com/\d+/\d+/geeks-guide', url):
    return wp_posts.get_content(url, args, save_debug)

  img_size = 'lg'
  json_url = url + '?format=json'
  article_json = utils.get_url_json(json_url)
  if not article_json:
    return None

  if save_debug:
    utils.write_file(article_json, './debug/debug.json')

  item = {}
  item['id'] = article_json['coreDataLayer']['content']['contentId']
  item['url'] = article_json['coreDataLayer']['page']['canonical']
  item['title'] = article_json['coreDataLayer']['content']['contentTitle']

  dt = datetime.fromisoformat(article_json['coreDataLayer']['content']['publishDate'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromisoformat(article_json['coreDataLayer']['content']['modifiedDate'].replace('Z', '+00:00'))
  item['date_modified'] = dt.isoformat()

  # Don't check age here. It should have been checked when parsing the RSS feed.

  item['author'] = {}
  item['author']['name'] = article_json['coreDataLayer']['content']['authorNames']

  if article_json['coreDataLayer']['content'].get('tags'):
    item['tags'] = article_json['coreDataLayer']['content']['tags'].split('|')

  item['_image'] = article_json['head.og.image']
  item['summary'] = article_json['head.description']

  page_type = article_json['head.pageType']
  body_json = article_json[page_type]['body']

  # Add lede image to article
  body_html = ''
  caption = ''
  img_url = ''
  if 'headerProps' in article_json[page_type] and 'lede' in article_json[page_type]['headerProps']:
    lede = article_json[page_type]['headerProps']['lede']
    if lede.get('contentType') == 'photo':
      if lede.get('caption'):
        m = re.search(r'<p>(.*)<\/p>', lede['caption'])
        if m:
          caption = m.group(1)
        else:
          caption = lede['caption']
      if lede.get('credit'):
        caption += ' ' + lede['credit']
      img_url = lede['sources'][img_size]['url']
    elif lede.get('contentType') == 'clip':
      if lede.get('caption'):
        m = re.search(r'<p>(.*)<\/p>', lede['caption'])
        if m:
          caption = m.group(1)
        else:
          caption = lede['caption']
      if lede.get('credit'):
        caption += ' ' + lede['credit']
      body_html += utils.add_video(lede['sources']['640w']['url'], 'video/mp4', caption=caption.strip())
    elif lede.get('metadata') and lede['metadata'].get('contentType') == 'cnevideo':
      video_json = utils.get_url_json('https://player.cnevids.com/embed-api.json?videoId=' + lede['cneId'])
      if video_json:
        for it in video_json['video']['sources']:
          if it['type'].find('mp4') > 0:
            body_html += utils.add_video(it['src'], it['type'], video_json['video']['poster_frame'], video_json['video']['title'])
  elif 'head.og.image' in article_json:
    img_url = article_json['head.og.image']
  elif item.get('_image'):
    img_url = item['_image']

  if img_url:
    body_html += utils.add_image(img_url, caption.strip())

  if page_type == 'review':
    body_html += '<h3>Rating: {}/{}</h3><p><em>PROS:</em> {}</p><p><em>CONS:</em> {}</p><hr/>'.format(article_json['review']['rating'], article_json['review']['bestRating'], article_json['review']['pros'], article_json['review']['cons'])

  def iter_body(body_json):
    nonlocal body_html
    nonlocal json_url

    tag = body_json[0]
    endtag = '</{}>'.format(tag)

    if tag == 'inline-embed':
      endtag = ''

      if re.search(r'\b(article|callout:anchor|callout:blockquote|callout:dropcap|callout:group-\d|callout:feature-large|callout:feature-medium|callout:inset-left|callout:inset-right|callout:sidebar|externallink|sidebar:article)\b', body_json[1]['type']):
        # skip
        pass

      elif body_json[1]['type'] == 'image':
        caption = ''
        if body_json[1]['props'].get('dangerousCaption'):
          m = re.search(r'<p>(.*)<\/p>', body_json[1]['props']['dangerousCaption'])
          if m:
            caption = m.group(1)
          else:
            caption = body_json[1]['props']['dangerousCaption']
        if body_json[1]['props'].get('dangerousCredit'):
          caption += ' ' + body_json[1]['props']['dangerousCredit']
        img_src = body_json[1]['props']['image']['sources'][img_size]['url']
        if not 'newsletter.png' in img_src:
          body_html += utils.add_image(img_src, caption.strip())

      elif body_json[1]['type'] == 'gallery':
        for it in body_json[1]['props']['slides']:
          caption = ''
          if 'dangerousCaption' in it:
            m = re.search(r'<p>(.*)<\/p>', it['dangerousCaption'])
            if m:
              caption = m.group(1)
            else:
              caption = it['dangerousCaption']
          if 'dangerousCredit' in it:
            caption += ' ' + it['dangerousCredit']
          body_html += utils.add_image(it['image']['sources'][img_size]['url'], caption.strip())

      elif body_json[1]['type'] == 'video':
        if 'youtube' in body_json[1]['props']['url']:
          body_html += utils.add_video(body_json[1]['props']['url'], 'youtube')
          #body_html += utils.add_youtube(body_json[1]['props']['url'], body_json[1]['props']['width'], body_json[1]['props']['height'])

      elif body_json[1]['type'] == 'clip':
        m = re.search(r'<p>(.*)<\/p>', body_json[1]['props']['dangerousCaption'])
        if m:
          caption = m.group(1)
        else:
          caption = body_json[1]['props']['dangerousCaption']
        caption += ' ' + body_json[1]['props']['dangerousCredit']

        videos = []
        for k in list(body_json[1]['props']['image']['sources'].keys()):
          videos.append(body_json[1]['props']['image']['sources'][k])
        video = utils.closest_dict(videos, 'height', 480)
        if body_html.find(quote_plus(video['url'])) < 0:
          body_html += utils.add_video(video['url'], 'video/mp4', None, caption.strip(), video['width'], video['height'])

      elif body_json[1]['type'] == 'cneembed':
        video_id = ''
        split_url = urlsplit(body_json[1]['props']['scriptUrl'])
        script_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, split_url.path)
        m = re.search(r'https:\/\/player\.cnevids\.com\/script\/video\/(\w+)\.js', body_json[1]['props']['scriptUrl'])
        if m:
          video_id = m.group(1)
        video_src = ''
        if video_id:
          video_json = utils.get_url_json('https://player.cnevids.com/embed-api.json?videoId=' + video_id)
          if video_json:
            for video_type in ['video/mp4', 'video/webm', 'application/x-mpegURL']:
              for it in video_json['video']['sources']:
                if it['type'] == video_type:
                  video_src = it['src']
                  break
              if video_src:
                break
        if video_src:
          body_html += utils.add_video(video_src, video_type, video_json['video']['poster_frame'], video_json['video']['title'])
        else:
          logger.warning('error with cneembed video {} in {}'.format(body_json[1]['props']['scriptUrl'], url))
  
      elif body_json[1]['type'] == 'cneinterlude':
        # Skip this - mostly seems to be related videos embedded in the middle of the article
        if False:
          for video_id in body_json[1]['props']['embeddedVideos']:
            video_src = ''
            video_json = utils.get_url_json('https://player.cnevids.com/embed-api.json?videoId=' + video_id)
            if video_json:
              for video_type in ['video/mp4', 'video/webm', 'application/x-mpegURL']:
                for it in video_json['video']['sources']:
                  if it['type'] == video_type:
                    video_src = it['src']
                    break
                if video_src:
                  break
            if video_src:
              body_html += utils.add_video(video_src, video_type, video_json['video']['poster_frame'], video_json['video']['title'])
            else:
              logger.warning('unable to get video info for videoId {} in {}'.format(video_id, url))

      elif body_json[1]['type'] == 'instagram':
        body_html += utils.add_instagram(body_json[1]['props']['url'])
  
      elif body_json[1]['type'] == 'twitter':
        tweet_url = body_json[1]['props']['url']
        tweet = utils.add_twitter(tweet_url)
        if tweet:
          body_html += tweet
        else:
          logger.warning('unable to add tweet {} in {}'.format(tweet_url, url))

      elif body_json[1]['type'] == 'iframe':
        if 'youtube' in body_json[1]['props']['url']:
          body_html += utils.add_video(body_json[1]['props']['url'], 'youtube')

        elif 'podcasts.apple' in body_json[1]['props']['url']:
          body_html += utils.add_apple_podcast(body_json[1]['props']['url'])

        elif re.search('(music|podcasts)\.apple', body_json[1]['props']['url']):
          embed = apple.get_content(body_json[1]['props']['url'], {"max": 5}, False)
          if embed:
            body_html += embed['content_html']

        elif 'bandcamp' in body_json[1]['props']['url']:
          embed = bandcamp.get_content(body_json[1]['props']['url'], {}, False)
          if embed:
            body_html += embed['content_html']

        elif 'soundcloud' in body_json[1]['props']['url']:
          embed = soundcloud.get_content(body_json[1]['props']['url'], {}, False)
          if embed:
            body_html += embed['content_html']

        elif 'spotify' in body_json[1]['props']['url']:
          embed = spotify.get_content(body_json[1]['props']['url'], {"max": 5}, False)
          if embed:
            body_html += embed['content_html']

        elif 'megaphone' in body_json[1]['props']['url']:
          body_html += utils.add_megaphone(body_json[1]['props']['url'])

        else:
          logger.warning('unhandled iframe {} in {}'.format(body_json[1]['props']['url'], url))
          body_html += '<iframe width="{}" height="{}" frameBorder="0" src="{}"></iframe>'.format(body_json[1]['props']['width'], body_json[1]['props']['height'], body_json[1]['props']['url'])

      elif body_json[1]['type'] == 'product':
        if not 'subscribe.wired.com' in body_json[1]['props']['offerUrl']:
          h = 2
          offer_html = ''
          if body_json[1]['props'].get('multipleOffers'):
            for offer in body_json[1]['props']['multipleOffers']:
              offer_html += '<li><a href="{}">{} &ndash; {}</a></li>'.format(offer['offerUrl'], offer['sellerName'], offer['price'])
              h = h + 2
          else:
            offer_html += '<li><a href="{}">{}</a></li>'.format(offer['offerUrl'], offer['offerRetailer'])
            h += 2
          if body_json[1]['props'].get('image'):
            body_html += '<table><tr><td style="padding:10px;"><img style="height:{}em;" src={} /></td><td><b>{}</b><ul>{}</ul></td></tr></table>'.format(h, body_json[1]['props']['image']['sources']['sm']['url'], body_json[1]['props']['dangerousHed'], offer_html)
          else:
            body_html += '<p><b>{}</b></p><ul>{}</ul>'.format(body_json[1]['props']['dangerousHed'], offer_html)

      elif body_json[1]['type'] == 'callout:align-center':
        body_html += '<div style="text-align: center">'
        endtag = '</div>'

      elif body_json[1]['type'] == 'callout:pullquote':
        body_html += '<blockquote style="border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;">'
        endtag = '</blockquote>'

      else:
        logger.warning('unhandled inline-embed type {} in {}'.format(body_json[1]['type'], json_url))

    elif tag == 'ad' or tag == 'native-ad' or tag == 'inline-newsletter':
      # skip
      return

    else:
      if tag == 'div':
        # Change heading tags from div's to h1, h2, h3, etc
        if 'role' in body_json[1] and body_json[1]['role'] == 'heading':
          # Skip the Related Stories heading
          try:
            if re.search(r'Related Stories', body_json[2], flags=re.I):
              return
          except:
            pass
          # Check if there's a newsletter sign up link, etc to skip
          try:
            if body_json[2][0] == 'a':
              if '/newsletter/' in body_json[2][1]['href']:
                return
          except:
            pass
          tag = 'h' + body_json[1]['aria-level']
          endtag = '</{}>'.format(tag)

      body_html += '<{}>'.format(tag)

    for i in range(1, len(body_json)):
      # Strings should be text
      if isinstance(body_json[i], str):
        body_html += body_json[i]

      # Dicts have props for the current tag
      elif isinstance(body_json[i], dict):
        if tag != 'inline-embed':
          body_html = body_html.rstrip('>')
          for key in body_json[i]:
            body_html += ' {}="{}"'.format(key, body_json[1][key])
          body_html += '>'

      # Lists are tags we iterate into
      elif isinstance(body_json[i], list):
        iter_body(body_json[i])

    body_html += endtag
    return

  iter_body(body_json)

  if page_type == 'gallery':
    for it in article_json[page_type]['items']:
      body_html += '<hr />'
      if it.get('image'):
        caption = ''
        if 'caption' in it['image']:
          m = re.search(r'<p>(.*)<\/p>', it['image']['caption'])
          if m:
            caption = m.group(1)
          else:
            caption = it['image']['caption']
        if 'credit' in it['image']:
          caption += ' ' + it['image']['credit']

        if img_size in it['image']['segmentedSources']:
          images = it['image']['segmentedSources'][img_size]
        else:
          # Default to sm
          images = it['image']['segmentedSources']['sm']
        for image in images:
          if image['height'] > 480 and image['height'] < 1000:
            break
        body_html += utils.add_image(image['url'], caption.strip())
      body_html += '<h3>{}</h3><h4>{} {}</h4>'.format(it['dangerousHed'], it['brand'], it['name'])
      iter_body(it['dek'])
      for offer in it['offers']:
        body_html += '<p><a href="{}">{} at {}</a></p>'.format(offer['offerUrl'], offer['price'], offer['sellerName'])

  def sub_lead_in_text_callout(matchobj):
    return '{}{}{}'.format(matchobj.group(1), matchobj.group(2).upper(), matchobj.group(3))
  body_html = re.sub(r'(lead-in-text-callout[^>]*>)([^<]*)(<)', sub_lead_in_text_callout, body_html)

  item['content_html'] = body_html
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)