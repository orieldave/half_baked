#!/usr/bin/env python3

"""
    Flask app to compute ferment times/temps for baking.
"""

import re
import os
import math
from datetime import datetime, timedelta
#from datetime.datetime import strptime

# Flask
from flask import Flask, request, session, redirect, \
    url_for, render_template


### CLASSES

class Ferment:
    """Fermentation step for a specified time, temp and inoculation.

    Time and temperature are fixed by the following formula:
        new_temp = old_temp - c * log(new_time / old_time)
    where:
        c = double_temp / log(2)
    and double_temp is therefore the increase/decrease in temperature
    required to halve/double the ferment time. Heuristically for bread,
    this is set at 8 C (17 F).

    Time and inoculation (as a percentage) are fixed by the following formula:
        new_time = old_time * (old_inoc / new_inoc)
    such that a doubling in the inoculation percentage will halve the time.
    """

    # Defaults
    default_double_temp = 8.0
    default_temp = 20.0
    default_inoc = 10.0

    def __init__(
            self, name, hours=None, start_time=None, end_time=None,
            temp=default_temp, double_temp=default_double_temp,
            inoc=default_inoc):
        """
        Init with time (in hours or start/end), temp (C) and inoculation (%).

        If hours is None, it is calculated from start/end times.
        """

        self.name = name
        self.temp = float(temp)
        self.double_temp = float(double_temp)
        self.inoc = float(inoc)

        # Hours is either explicit or end_time - start_time
        if hours:
            self.hours = float(hours)
        else:
            self.hours = float((end_time - start_time).seconds/3600)

        # Start is either expicit or end_time - hours
        self.start_time = start_time
        if (start_time is None) and (end_time is not None):
            self.start_time = end_time - timedelta(hours=hours)


    def get_args(self):
        """Return dict of init args."""

        init_args = {
            'name': self.name,
            'hours': self.hours,
            'start_time': self.start_time,
            'temp': self.temp,
            'double_temp': self.double_temp,
            'inoc': self.inoc
            }

        return init_args


    def get_end_time(self):
        """Return self.start_time offset by self.hours"""

        if self.start_time:
            return self.start_time + timedelta(hours=self.hours)
        else:
            return None


    def change_hours(self, new_hours, hold='inoc'):
        """Change ferment time in hours, adjust temp or inoc accordingly.

        Temperature is set by:
            new_temp = old_temp - c * log(new_time / old_time)
        where
            c = double_temp / log(2)

        Inoculation is set by:
            new_inoc = old_inoc * (old_time / new_time)
        """

        if hold != 'temp':
            # Adjust temperature, holding inoc
            c = self.double_temp / math.log(2)
            new_temp = self.temp - (c * math.log(float(new_hours) / self.hours))
            self.temp = new_temp
        else:
            # Adjust inoculation, holding temp
            new_inoc = self.inoc * (self.hours / new_hours)
            self.inoc = new_inoc

        # Adjust hours
        self.hours = float(new_hours)


    def change_temp(self, new_temp, hold='inoc'):
        """Change ferment temp in C, adjust time (in hours) or inoc accordingly.

        Time is set by:
            new_time = old_time * exp((old_temp - new_temp) / c)
        where
            c = double_temp / log(2)
        """

        # Adjust hours, holding inoc
        inv_c = math.log(2) / self.double_temp
        old_hours = self.hours
        new_hours = old_hours * math.exp(inv_c * (self.temp - float(new_temp)))
        self.hours = new_hours
        self.temp = float(new_temp)

        if hold == 'hours':
            # Change hours back to old_hours, holding temp
            # This will adjust inoculation without an explicit formula
            self.change_hours(old_hours, hold='temp')


    def change_inoc(self, new_inoc, hold='temp'):
        """Change inoculation percent, adjust hours or temp accordingly.

        Time is set by:
            new_time = old_time * (old_inoc / new_inoc)
        """

        # Adjust hours, holding temp
        old_hours = self.hours
        new_hours = old_hours * (self.inoc / float(new_inoc))
        self.hours = new_hours
        self.inoc = float(new_inoc)

        if hold == 'hours':
            # Change hours back to old_hours, holding inoc
            # This will adjust temp without an explicit formula
            self.change_hours(old_hours, hold='inoc')


    def change_times(self, new_start_time=None, new_end_time=None, hold='inoc'):
        """Set start/end time. If both are given, change hours too."""

        if new_start_time:
            if new_end_time:
                self.change_hours(
                    (new_end_time - new_start_time).seconds/3600, hold=hold
                    )
            self.start_time = new_start_time

        elif new_end_time:
            self.start_time = new_end_time - timedelta(hours = self.hours)

        else:
            self.start_time = None


    # Printing

    def get_name_str(self):
        """Return string of self.name."""
        return '{}'.format(self.name)

    def get_time_str(self):
        """Return string of self.time."""
        return '{:.2f}'.format(self.hours)

    def get_inoc_str(self):
        """Return string of self.inoc."""
        return '{:.1f}'.format(self.inoc)

    def get_temp_str(self):
        """Return string of self.temp."""
        return '{:.1f}'.format(self.temp)

    def get_start_str(self):
        """Return string of self.start_time."""
        if self.start_time is not None:
            return '{:%a %H.%M}'.format(self.start_time)
        else:
            return 'None'

    def get_end_str(self):
        """Return string of self.get_end_time."""

        if self.start_time is not None:
            return '{:%a %H.%M}'.format(self.get_end_time())
        else:
            return 'None'

    def get_double_time_str(self):
        """Return string of self.double_time."""

        return '{:.2f}'.format(self.double_temp)


    ### TESTING ###

    def print_name(self):
        """Print name."""

        print(self.get_name_str())

    def print_values(self, verbose=False):
        """Print all values."""

        self.print_name()
        print(self.get_time_str())
        print(self.get_temp_str())
        print(self.get_inoc_str())

        if self.start_time is not None:
            print(self.get_start_str())
            print(self.get_end_str())

        if verbose:
            print(self.get_double_time_str())



class Bake:
    """Bake sequence consisting of multiple fermentation steps.

    Each stage is a separate Ferment object with start times synced
    to ensure no gaps between stages.

    Default stages (at 20C):
        1. Refresh (24 hours, 18 inoculation)
        2. Feed (8 hours, 10 inoculation)
        3. Bulk (12 hours, 15 inoculation)
        4. Proof (2 hours, 100 inoculation)
    """

    # Defaults
    default_args = {
        'temp': 20.0
        }

    default_ferment_list = [
        {'name': 'refresh', 'hours': 24, 'temp': 20.0, 'inoc': 18},
        {'name': 'feed', 'hours': 8, 'temp': 20.0, 'inoc': 10},
        {'name': 'bulk', 'hours': 12, 'temp': 20.0, 'inoc': 15},
        {'name': 'proof', 'hours': 2, 'temp': 20.0, 'inoc': 100}
        ]

    def __init__(self, ferment_list=default_ferment_list, name=None):
        """Create bake object from list of ferment args for each stage.

        Args:
            * ferment_args: list of dicts of ferment object args
            * name: string name for object
        """

        self.name = name
        self.ferments = []
        self.update_ferment_index()

        for ferment_args in ferment_list:
            self.add_ferment(**ferment_args)


    def get_args(self):
        """Return dict of init args."""

        init_args = {
            'name': self.name,
            'ferment_list': [
                ferment.get_args() for ferment in self.ferments
                ]
            }

        return init_args


    def add_ferment(self, index=None, **ferment_args):
        """
        Create ferment object from ferment args, append to self.ferments list.

        Args:
        * ferment_args -- keyword args for creating ferment object
        * index -- int, index to insert to instead of append

        Any args in default_args are applied if not specified in ferment_args.
        If index is not None, insert is used, otherwise append.
        """

        # Add args from defaults if not in ferment_args
        for k, v in self.default_args.items():
            if (k not in ferment_args.keys()) \
                or (ferment_args[k] is None):

                ferment_args[k] = v

        # Make ferment from ferment_args
        ferment = Ferment(**ferment_args)

        # Check ferment.name is unique and append '_' if not
        while ferment.name in self.ferment_index.keys():
            ferment.name = '{}_'.format(ferment.name)

        if index is None:
            index = len(self.ferments)

        self.ferments.insert(index, ferment)
        self.update_ferment_index()
        self.sync_times(index)


    def remove_ferment(self, index):
        """Remove ferment from bake, specified by index."""

        del self.ferments[index]
        self.update_ferment_index()
        self.sync_times()


    def update_ferment_index(self):
        """
        Update dict of name:index to be consistent with list of
        ferments.
        """

        self.ferment_index = {
            f.name: index for (index, f) in enumerate(self.ferments)
            }


    def sync_times(self, index=0):
        """
        Adjust start_time of each ferment, using index ferment as
        reference.

        From reference ferment, change other start times to ensure no
        gaps between ferments.
        Never changes length of ferments (ferment.hours).

        If index ferment.start_time is not None, uses this as reference.
        Else if some other not None start_time, uses this.
        Else do nothing (all start_times are None).
        """

        n_ferments = len(self.ferments)

        if n_ferments > 0:
            # Search for not None start_time in ferments,
            # starting with index
            ref_index = None
            for i in [index] + list(range(n_ferments)):
                if self.ferments[i].start_time is not None:
                    ref_index = i
                    break

            if ref_index is not None:
                for i in range(ref_index+1, n_ferments):
                    # Set next_start_time = prev_end_time
                    start_time_i = self.ferments[i-1].get_end_time()
                    self.ferments[i].change_times(start_time_i)

                for i in range(ref_index-1, -1, -1):
                    # Set prev_start_time = start_time - prev_hours
                    start_time_i = self.ferments[i+1].start_time \
                        - timedelta(hours = self.ferments[i].hours)
                    self.ferments[i].change_times(start_time_i)


    def change_times(self, index, start_time=None, end_time=None, hold='inoc'):
        """Change start_time of index ferment."""
        # Change start_time (and hours if end_time is specified)
        self.ferments[index].change_times(start_time, end_time, hold=hold)
        self.sync_times(index)

    def change_hours(self, index, hours, hold='inoc'):
        """Change hours of index ferment."""

        self.ferments[index].change_hours(hours, hold=hold)
        self.sync_times(index)

    def change_temp(self, index, temp, hold='inoc'):
        """Change temp of index ferment."""

        self.ferments[index].change_temp(temp, hold=hold)
        self.sync_times(index)

    def change_inoc(self, index, inoc, hold='temp'):
        """Change inoc of index ferment."""

        self.ferments[index].change_inoc(inoc, hold=hold)
        self.sync_times(index)

    def get_n_ferments(self):
        """"""
        return len(self.ferments)

    # Printing

    def get_name_str(self):
        """Return string of self.name."""
        return '{}'.format(self.name)


    def get_ferment_name_str(self, ferment):
        """Return string of self.name."""

        index = self.ferment_index[ferment.name]
        return '{}. Ferment "{}"'.format(index+1, ferment.get_name_str())


    def print_bake(self, verbose=True):
        """Print name of each ferment, also values if verbose == True."""

        print('\nBake "{}"'.format(self.name))
        for ferment in self.ferments:
            print('Index: \t{}'.format(self.ferment_index[ferment.name]))
            if verbose:
                ferment.print_values()
                print('')
            else:
                ferment.print_name()


# Datetime helper functions

def html_strptime(s):
    """"""
    html_format = '%Y-%m-%dT%H:%M'
    return datetime.strptime(s, html_format)


def strp_day_time(s):
    """Take string in format '%a %H.%M', return datetime if possible.

    Finds next date after current date with that day.
    Eg. given 'fri 09.00', if today is Weds Jan 1st, returns Fri Jan 3rd.
    """

    day_format = '%a'
    time_format = '%H.%M'
    # Check if valid day and time
    try:
        _ = datetime.strptime(s, '{} {}'.format(day_format, time_format))
        # This may have the wrong day of week, because will be 01-01-1900
    except Exception as ee:
        return None
    # This is a valid day and time, but must find  a valid date
    target_day, target_time = s.split()
    target_hour, target_min = [
        int(digits) for digits in target_time.split('.')
        ]
    # Current date
    today = datetime.today()
    today_time = datetime.strftime(today, time_format)
    # Find first date of correct day on/after current date
    if target_time >= today_time:
        return_date = today
    else:
        return_date = today + timedelta(days=1)
    # Set return time
    return_date = return_date.replace(
        hour=target_hour, minute=target_min, second=0, microsecond=0
        )
    # Find next date with correct day of week
    while datetime.strftime(return_date, day_format).lower() \
        != target_day.lower():
        # Increment days until return_day == target_day
        return_date = return_date + timedelta(days=1)

    return return_date


def parse_day_time_str(s):
    """
    Coerce string into '%a %H.%M' format, eg. 'mon 09.00', return datetime.

    Splits string on spaces,
    filters each word into 'day' and 'time' candidates,
    attempts to convert these to datetimes using strp_day_time,
    returns first not None match
    else returns None.
    """

    days = []
    times = []
    l = s.split()
    for word in l:
        # Sub digits, then non-word, lower
        word_day = re.sub('[^\w]', '', re.sub('\d', '', word))[:3]
        if len(word_day) == 3:
            days.append(word_day.lower())
        # Sub non-digits
        word_time = re.sub('[^\d]', '', word)[:4]
        if len(word_time) == 4:
            times.append('{}.{}'.format(word_time[:2], word_time[-2:]))

    for day in days:
        for time in times:
            clean_day_time = '{} {}'.format(day, time)
            day_time_date = strp_day_time(clean_day_time)
            if day_time_date is not None:
                return day_time_date
    return None




### FLASK
app = Flask(__name__) # create the application instance
app.config.from_object(__name__) # load config from this file

# Load default config and override config from
# environment variable pointing to file
app.config.update(dict(
    DEBUG=True,
    SECRET_KEY='test'
    ))

app.config.from_envvar('HALFBAKED_CONFIG', silent=True)


@app.route('/', methods=['GET', 'POST'])
def home():
    """Home page."""

    if request.method == 'POST':
        bake_name = request.form['bake_name']
        if request.form['create'] == 'Default':
            session['bake_args'] = {'name': bake_name}
        else:
            session['bake_args'] = {
                'ferment_list': [], 'name': bake_name
                }
        return redirect(url_for('show_bake'))
    return render_template('home.html')


@app.route('/show_bake', methods=['GET', 'POST'])
def show_bake():
    """Show bake."""

    if not session.get('bake_args'):
        return redirect(url_for('home'))
    else:
        bake = Bake(**session['bake_args'])
        return render_template('show_bake.html', bake=bake)


@app.route('/add_ferment/<int:ferment_index>', methods=['GET', 'POST'])
def add_ferment(ferment_index):
    """Add ferment at position <ferment_index>."""

    # Create bake object from bake_args
    bake = Bake(**session['bake_args'])

    if request.method == 'POST':
        if request.form['add_or_cancel'] == 'Cancel':
            # Return to show_bake
            return redirect(url_for('show_bake'))
        else:
            # Process inputs
            inputs = [
                'ferment_name', 'ferment_temp', 'ferment_time',
                'ferment_inoc', 'ferment_start', 'ferment_end'
                ]
            cast_funcs = [
                str, float, float, float, parse_day_time_str, parse_day_time_str
                ]
            values = {k:None for k in inputs}
            casts = {k:f for k,f in zip(inputs, cast_funcs)}

            for k in inputs:
                val = request.form[k]
                if len(val) > 0:
                    values[k] = casts[k](val)

            bake.add_ferment(
                ferment_index,
                name=values['ferment_name'],
                temp=values['ferment_temp'],
                hours=values['ferment_time'],
                inoc=values['ferment_inoc'],
                start_time=values['ferment_start'],
                end_time=values['ferment_end']
                )

            session['bake_args'] = bake.get_args()
            return redirect(url_for('show_bake'))

    return render_template(
        'add_ferment.html', ferment_index=ferment_index
        )

@app.route('/edit_ferment/<ferment_name>', methods=['GET', 'POST'])
def edit_ferment(ferment_name):
    """Edit ferment <ferment_name>."""

    # Create bake object from bake_args
    bake = Bake(**session['bake_args'])
    ferment_index = bake.ferment_index[ferment_name]
    ferment = bake.ferments[ferment_index]

    if request.method == 'POST':
        if request.form['add_or_cancel'] == 'Cancel':
            # Return to show_bake
            return redirect(url_for('show_bake'))
        else:
            # Process inputs
            inputs = [
                'ferment_temp', 'ferment_time', 'ferment_inoc',
                'ferment_start', 'ferment_end'
                ]
            cast_funcs = [
                float, float, float, parse_day_time_str, parse_day_time_str
                ]
            values = {k:None for k in inputs}
            casts = {k:f for k,f in zip(inputs, cast_funcs)}

            for k in inputs:
                val = request.form[k]
                if len(val) > 0:
                    values[k] = casts[k](val)

            # Change one or more of temp, time, inoc, one at a time
            # Hold the previously changed value fixed
            # It only makes sense to change two of the three

            # Default value to hold
            hold = 'inoc'

            if values['ferment_inoc'] is not None:
                # Change inoculation (hold temp by default)
                bake.change_inoc(ferment_index, values['ferment_inoc'], 'temp')
                hold = 'inoc'

            if values['ferment_temp'] is not None:
                # Change temp
                bake.change_temp(ferment_index, values['ferment_temp'], hold)
                hold = 'temp'

            if values['ferment_time'] is not None:
                # Change hours
                bake.change_hours(ferment_index, values['ferment_time'], hold)
                # Don't update 'hold' variable, in case start/end times are
                # also changing

            if (values['ferment_start'] is not None) \
                or (values['ferment_end'] is not None):
                # Then change times
                bake.change_times(
                    ferment_index, values['ferment_start'],
                    values['ferment_end'], hold
                    )

            session['bake_args'] = bake.get_args()
            return redirect(url_for('show_bake'))

    return render_template(
        'edit_ferment.html', ferment=ferment
        )


@app.route('/delete_ferment/<ferment_name>', methods=['GET', 'POST'])
def delete_ferment(ferment_name):
    """Delete ferment."""

    bake = Bake(**session['bake_args'])
    bake.remove_ferment(bake.ferment_index[ferment_name])
    session['bake_args'] = bake.get_args()

    return redirect(url_for('show_bake'))
