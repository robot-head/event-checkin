import csv
import constants
import json
import model


class TicketFileParser(object):
  
  def __init__(self, ticket_file, event):
    self.ticket_file = ticket_file
    self.event = event
    
  def Parse(self):
    pass


class CsvTicketFileParser(TicketFileParser):
  
  key_position = 1
  
  def Parse(self):
    reader = csv.reader(self.ticket_file)
    header = reader.next()
    self.event.descriptor_format = json.dumps(header)
    self.event.put()
    for row in reader:
      key = row[self.key_position]
      ticket = model.Ticket(
          code=key, event=self.event, status=constants.STATUS.UNCLAIMED,
          descriptor=json.dumps(row))
      ticket.put()
      