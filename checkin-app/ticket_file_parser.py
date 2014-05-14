import csv
import json
import model


class Error(Exception): pass
class DuplicateTicketError(Error): pass
class InvalidRowError(Error): pass


class TicketFileParser(object):
  
  def __init__(self, ticket_file, event):
    self.ticket_file = ticket_file
    self.event = event
    
  def Parse(self):
    pass


class CsvTicketFileParser(TicketFileParser):
  
  key_position = 1
  _keys = []
  _rowlen = 0
  
  def Parse(self):
    reader = csv.reader(self.ticket_file)
    header = reader.next()
    self._rowlen = len(header)
    self.event.descriptor_format = json.dumps(header)
    self.event.put()
    for row in reader:
      if len(row) != self._rowlen:
        raise InvalidRowError(
            'Expected %s columns but found %s. Row: %s' % (
                self._rowlen, len(row), row))
      key = row[self.key_position]
      if key in self._keys:
        raise DuplicateTicketError('Already seen key %s' % key)
      self._keys.append(key)
      ticket = model.Ticket(
          code=key, event=self.event, claim_count=0,
          descriptor=json.dumps(row))
      ticket.put()
      
