import os, shutil, argparse, logging, sys, subprocess, requests
from zipfile import ZipFile

logging.basicConfig(format='%(message)s', stream=sys.stdout, level=logging.INFO)

mode_gender = 'n'
mode_lang = 'en'

path_to_roms = "roms"

def main():
    global mode_gender
    global mode_lang
    global mode_yuusha

    parser = argparse.ArgumentParser(description='Patch English script files for JP Dragon Quest IV ROM.')
    parser.add_argument('--file', help='File to be patched. must be present in the ./en directory. Disables automatic extracting and repacking.', default=None)
    parser.add_argument('--yuusha', help='Player character name. Maximum 7 characters.', default='')
    parser.add_argument('--gender', help='[(n)|m|f|b] player character gender. options are neutral, male, female, both', default='n')
    parser.add_argument('--lang', help='[(en)|ja] rom language mode to target. en uses nametags, ja embeds the speaker name in text', default='en')
    parser.add_argument('--debug', dest='debug', action='store_true', help='Enable debug logs')
    parser.add_argument('--manual', help='Does not run the automatic extractor or repacker. You will have to extract and repack the files yourself.', action='store_true')

    args = parser.parse_args()

    if args.gender not in ['n', 'm', 'f', 'b']:
        logging.error(f'Unsupported --gender: {args.gender}')
        exit(1)
    if args.lang not in ['en', 'ja']:
        logging.error(f'Unsupported --lang: {args.lang}')
        exit(1)
    if len(args.yuusha) > 7:
        logging.error(f'Hero name must be 7 characters or less. Zannen desu.')
        exit(1)
    if args.debug:
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
    mode_gender = args.gender
    mode_lang = args.lang
    mode_manual = args.manual
    path_to_ndstool = "ndstool"

    logging.info(f"Patching directory en, writing results to 'out/{mode_lang}'")
    
    shutil.rmtree("out", ignore_errors=True)
    os.mkdir("out")
    os.mkdir(f"out/{mode_lang}")

    if args.file is not None:
        mode_manual = True
        patch_file_en(args.file)
    else:
        if not mode_manual:
            path_to_ndstool = automatic_extract_repack()
        
        files = os.listdir('en')
        for file in files:
            patch_file_en(f'{file}')

    if not mode_manual:
        repack(mode_gender=mode_gender, mode_lang=mode_lang, path_to_ndstool=path_to_ndstool)

    # Prologue
    # patch_file_en("b0200000.mpt")

    # Plurals
    # patch_file_en("b0803000.mpt")

    # Nested
    # patch_file_en("b0802000.mpt")

    # Party-specific
    # patch_file_en("b0018000.mpt")

    # Chapter titles (special case)
    # patch_file_en("b1007000.mpt")

    # Battle text
    # patch_file_en('b0801000.mpt')

def is_control_char(bytes):
    return is_regular_control_char(bytes) or is_gender_control_char(bytes)

def is_regular_control_char(bytes):
    return bytes == b'%H' or bytes == b'%M' or bytes == b'%O' or bytes == b'%L' or bytes == b'%D'

def is_regular_secondary_control_char(bytes):
    return bytes == b'%Y'

def is_gender_control_char(bytes):
    return bytes == b'%A'

def is_gender_secondary_control_char(bytes):
    return bytes == b'%B' or bytes == b'%C'

def replace_control_segment(control_char, options):
    assert is_control_char(control_char), f'Attempted to replace non-control-char: {control_char}'

    if control_char == b'%H':
        # Rewrite %H***%X<singular>%Y<plural>%Z blocks. Use the plural variant for these blocks.
        return options[len(options)-1]
    elif control_char == b'%M':
        # Rewrite %M***%X<plural>%Y<singular>%Z blocks. Use the singular variant for these blocks.
        return options[len(options)-1]
    elif control_char == b'%O':
        # Rewrite %O***%X<party member>%Y<other party member>%Z blocks. 
        # Use the second variant since it seems more generally applicable.
        return options[1]
    elif control_char == b'%L':
        # Rewrite %L***%X<both sisters>%Y<one sister>%Z blocks. Use the second variant.
        return options[1]
    elif control_char == b'%D':
        # Rewrite %D120%Xyourself%Yyourselves%Z blocks, used only by Hank Hoffman Jr. Use the secpnd option.
        return options[1]
    elif control_char == b'%A':
        # Rewrite %A***%X<masculine>%Z%B***%X<feminine>%Z%C***%X<non-gendered>%Z blocks 
        # using specific gender mode or rule-based replacement.
        if mode_gender == 'b':
            return bytearray('/', 'utf-8').join(options)
        elif mode_gender == 'm':
            return options[0]
        elif mode_gender == 'f':
            if len(options) > 1:
                return options[1]
            return options[0]

        # Rule-based replacement
        if len(options) == 1:
            logging.warning(f'**** WARNING ****: Gender block has only one choice: {options[0]}')
            return options[0]
        else:
            if options[0] == b'his':
                return b'their'
            if options[0] == b'he':
                return b'they'
            if options[0] == b'man':
                return b'person'
            if options[0] == b'him':
                return b'them'
            if options[0] == b'himself':
                return b'themself'
            if options[0] == b'feen':
                return b'person' 
            if options[0] == b'laddie':
                return b'child'
            if options[0] == b'his':
                return b'their'
            if options[0] == b'gent':
                return b'one'
            if options[0] == b'monsieur':
                return b'friend'
            if options[0] == b'son':
                return b'young one'
            if options[0] == b'o mighty hero':
                return b'o mighty warrior'
            if options[0].find(b'guy') >= 0:
                return b'person'
            if options[0].find(b'sir') >= 0:
                return b'friend'
            if options[0].find(b'boy') >= 0:
                return b'young one'
            if options[0].find(b'ero') >= 0 and options[1].find(b'eroine') >= 0:
                return b'warrior'
            logging.warning(f'**** WARNING ****: Unhandled gender replacement, falling back to first: {options[0]}')
            return options[0]
    raise

def reduce_control_segment(segment):
    is_regular = is_regular_control_char(segment[0:2])
    is_gender = is_gender_control_char(segment[0:2])
    assert is_regular or is_gender, f'Attempted to reduce non-control segment: {segment}'
    if is_gender:
        return reduce_gender_control_segment(segment)
    return reduce_regular_control_segment(segment)

def reduce_regular_control_segment(segment):
    size = len(segment)

    pointer = 0
    # Control segment starts appear to always be 7 bytes
    pointer = pointer + 7

    options = [bytearray("", 'utf-8')]
    options_index = 0

    while pointer < size:
        if is_control_char(segment[pointer:pointer+2]):
            rcs, cs = reduce_control_segment(segment[pointer:])
            pointer += len(cs)
        elif is_regular_secondary_control_char(segment[pointer:pointer+2]):
            options.append(bytearray("", 'utf-8'))
            options_index += 1
            pointer += 2
        elif segment[pointer:pointer+2] == b'%Z':
            pointer += 2
            break
        else:
            options[options_index].append(segment[pointer])
            pointer += 1

    control_segment = segment[0:pointer]
    reduced_control_segment = replace_control_segment(segment[0:2], options)

    logging.debug(f'***Found control segment: {control_segment}***')
    logging.debug(f'***Reduced control segment: {reduced_control_segment}***')
    logging.debug(f'Regular options: {options}')

    return reduced_control_segment, control_segment

def reduce_gender_control_segment(segment):
    size = len(segment)

    pointer = 0
    # Control segment starts appear to always be 7 bytes
    pointer = pointer + 7

    options = [bytearray("", 'utf-8')]
    options_index = 0

    while pointer < size:
        if is_control_char(segment[pointer:pointer+2]):
            rcs, cs = reduce_control_segment(segment[pointer:])
            pointer += len(cs)
        elif is_gender_secondary_control_char(segment[pointer:pointer+2]):
            options.append(bytearray("", 'utf-8'))
            options_index += 1
            pointer += 7
        elif segment[pointer:pointer+2] == b'%Z':
            pointer += 2
            # Check if we have any further gender options after this one.
            # If not, we can end.
            if not is_gender_secondary_control_char(segment[pointer:pointer+2]):
                break
        else:
            options[options_index].append(segment[pointer])
            pointer += 1

    control_segment = segment[0:pointer]
    reduced_control_segment = replace_control_segment(segment[0:2], options)

    logging.debug(f'***Found gender control segment: {control_segment}***')
    logging.debug(f'***Reduced gender control segment: {reduced_control_segment}***')
    logging.debug(f'Gender options: {options}')

    return reduced_control_segment, control_segment

def process_control_chars(segment):
    size = len(segment)
    # Step through segment 
    processed_segment = bytearray("", 'utf-8')

    pointer = 0
    while pointer < size:
        if is_control_char(segment[pointer:pointer+2]):
            reduced_control_segment, control_segment = reduce_control_segment(segment[pointer:])
            processed_segment.extend(reduced_control_segment)
            pointer += len(control_segment)
        else:
            # Write the current byte as-is
            processed_segment.append(segment[pointer])
            pointer += 1

    return processed_segment

def fix_grammar(segment):
    fixed_segment = segment
    fixed_segment = fixed_segment.replace(b"they's", b"they are")
    fixed_segment = fixed_segment.replace(b'weve ', b"we've")
    fixed_segment = fixed_segment.replace(b'Weve ', b"We've")
    fixed_segment = fixed_segment.replace(b"What luck!", b"Found")
    fixed_segment = fixed_segment.replace(b'they cares', b'they care')
    return bytearray(fixed_segment)

def reflow_segment(segment, force=False, reflow_limit=43, newline_end=True):
    # Check if we need to reflow at all. If not, return the original segment.
    needs_reflow = force
    lines = segment.split(b'\n')
    for line in lines:
        if len(line) > reflow_limit:
            needs_reflow = True
            break
    if not needs_reflow:
        return bytearray(segment)

    # Convert all newlines to spaces.
    reflowed_segment = bytearray(segment.replace(b'\n', b' '))

    # Break segment into lines of max reflow_limit chars.
    size = len(segment)
    pointer = 0
    current_line_size = 0
    last_space_index = None
    while pointer < size:
        if reflowed_segment[pointer] == ord(' '):
            last_space_index = pointer
        if current_line_size > reflow_limit and last_space_index is not None:
            reflowed_segment[last_space_index] = ord('\n')
            current_line_size = pointer - last_space_index
            last_space_index = None
        else:
            current_line_size += 1 
        pointer += 1

    reflowed_size = len(reflowed_segment)
    if newline_end:
        if reflowed_segment[reflowed_size-1] == ord(' '):
            reflowed_segment[reflowed_size-1] = ord('\n')
    else:
        if reflowed_segment[reflowed_size-1] == ord('\n'):
            reflowed_segment[reflowed_size-1] = ord(' ')

    return reflowed_segment

# Process a single "segment" of dialogue.
# The resulting segment should be the exact same length as the original segment.
def process_segment(filename, segment):
    size = len(segment)

    # Strip all %0 control characters.
    segment = segment.replace(b'%0', b'')

    # Strip or replace special characters that aren't rendered correctly in English and show up as "%".
    segment = segment.replace(b'\xe2\x80\x94', b'-')
    segment = segment.replace(b'\xe2\x80\x98', b'"')
    segment = segment.replace(b'\xe2\x80\x99', b'"')
    segment = segment.replace(b'\xe3\x88\xa1', b'')
    segment = segment.replace(b'\xe2\x93\x86', b'')
    segment = segment.replace(b'\xe2\x93\x87', b'')
    segment = segment.replace(b'\xe2\x93\x95', b'')
    segment = segment.replace(b'\xe2\x93\x96', b'')
    segment = segment.replace(b'\xe2\x93\x97', b'')
    segment = segment.replace(b'\xe2\x93\x98', b'')
    segment = segment.replace(b'\xe2\x93\x99', b'')
    segment = segment.replace(b'\xe2\x99\xaa', b'~')

    processed_segment = process_control_chars(segment)

    # Fix grammar issues caused by replacements.
    processed_segment = fix_grammar(processed_segment)

    # Hardcode protagonist name if given.
    if len(mode_yuusha) > 0:
        processed_segment = processed_segment.replace(b'%a00090',bytes(mode_yuusha,'ascii'))

    # Reflow lines.
    if (filename == 'b0801000.mpt'):
        processed_segment = reflow_segment(processed_segment, True, 45, False)
        # Special case logic: 
        if processed_segment.find(b'appears!') >= 0 or processed_segment.find(b'appear!') >= 0:
            # Enemy name announcements should end with newline.
            processed_segment[len(processed_segment)-1] = ord('\n')
        if processed_segment.find(b'Each party member receives') >= 0:
            # Experience points message should not have any newlines.
            processed_segment = bytearray(processed_segment.replace(b'\n', b' '))
    else:
        processed_segment = reflow_segment(processed_segment, True, 43, False)
   
    # Perform special case reflow.
    segment_no_newlines = bytearray(processed_segment.replace(b'\n', b' '))

    special_case_str = b'exchanges their %a00102 '
    special_case_idx = segment_no_newlines.find(special_case_str)
    if (special_case_idx >= 0):
        processed_segment[special_case_idx + len(special_case_str) - 1] = ord(b'\n')
    special_case_str = b'puts their %a00100 '
    special_case_idx = segment_no_newlines.find(special_case_str)
    if (special_case_idx >= 0):
        processed_segment[special_case_idx + len(special_case_str) - 1] = ord(b'\n')
    special_case_str = b'puts %a02100 '
    special_case_idx = segment_no_newlines.find(special_case_str)
    if (special_case_idx >= 0):
        processed_segment[special_case_idx + len(special_case_str) - 1] = ord(b'\n')
    special_case_str = b'takes %a02100 '
    special_case_idx = segment_no_newlines.find(special_case_str)
    if (special_case_idx >= 0):
        processed_segment[special_case_idx + len(special_case_str) - 1] = ord(b'\n')
    special_case_str = b" Your custom's most appreciated."
    special_case_idx = segment_no_newlines.find(special_case_str)
    if (special_case_idx >= 0):
        processed_segment[special_case_idx] = ord(b'\n')

    # Perform special case line replacements.
    if segment_no_newlines.find(b"%a02010's %a00101 is exchanged for %a02180's %a00102.") >= 0:
        processed_segment = bytearray(b"%a02010's %a00101 is exchanged for\n%a02180's %a00102.")
    elif segment_no_newlines.find(b'%a02010 puts their %a00100 in a different place. ') >= 0:
        processed_segment = bytearray(b'%a02010 puts their %a00100\nin a different place. ')
    elif segment_no_newlines.find(b'%a00110 puts %a02100 in a different place in the bag. ') >= 0:
        processed_segment = bytearray(b'%a00110 puts %a02100\nin a different place in the bag. ')
    elif segment_no_newlines.find(b"I'll take that %a00100 off your hands for %a00620 gold coins. Okay?") >= 0:
        processed_segment = bytearray(b"I'll take that %a00100 off your\nhands for %a00620 gold coins. Okay?")
    elif segment_no_newlines.find(b"%a04100? I'll give you %a00620 gold coins for it. Okay?") >= 0:
        processed_segment = bytearray(b"%a04100? I'll give you %a00620\ngold coins for it. Okay?")
    # special case control character for yggdrasil leaf that doesn't have a good choice available.
    elif segment_no_newlines.find(b'%a02010 mashes up the Yggdrasil leaf and administers it to %N180%Xthemself%Y%a02180%Z.') >= 0:
        processed_segment = bytearray(b'%a02010 mashes up the\nYggdrasil leaf and administers it.')
    # typo in original script
    elif segment_no_newlines.find(b'*: May divine protection accompany the great , %a00090.') >= 0:
        processed_segment = bytearray(b'*: May divine protection accompany the\ngreat %a00090.')
    # better formatting for multiheal
    elif segment_no_newlines.find(b"%a02010's wounds heal! ") >= 0:
        processed_segment = bytearray(b"%a02010's wounds heal!\n")
    elif segment_no_newlines.find(b"%a02180's wounds heal! ") >= 0:
        processed_segment = bytearray(b"%a02180's wounds heal!\n")
    elif segment_no_newlines.find(b"%a02010 casts %a00170! ") >= 0:
        processed_segment = bytearray(b"%a02010 casts %a00170!\n")
    elif (segment_no_newlines.find(b"t notice the party's ") >= 0):
        # This line is rendered in small font and doesn't need any newlines.
        processed_segment = segment_no_newlines
    elif (segment_no_newlines.find(b"%a02180 takes %a02100 out of the bag.") >= 0):
        processed_segment = segment_no_newlines
    elif (segment_no_newlines.find(b"%a00120 puts %a02100 into the bag.") >= 0):
        processed_segment = segment_no_newlines
    elif (segment_no_newlines.find(b'%a02010 puts %a02100 in the bag.') >= 0):
        processed_segment = segment_no_newlines

    # Pad the processed segment to the same length as the original.
    logging.info(f'Processed segment: {bytes(processed_segment)}')
    while len(processed_segment) < size:
        processed_segment.extend(b' ')

    assert len(processed_segment) == size, f"ERROR: Processed segment size ({len(processed_segment)}) does not match original size ({size})"

    return processed_segment

def special_case_patch(filename, data):
    patched_data = data
    patched = False
    if filename == 'b1007000.mpt':
        patched_data = patched_data.replace(b'@1Chapter 1: Ragnar McRyan and the Case of the Missing Children@', b'@1Chapter 1: Ragnar McRyan\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE@')
        patched_data = patched_data.replace(b'@1Chapter 2: Alena and the Journey to the Tourney@', b'@1Chapter 2: Alena\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE@')
        patched_data = patched_data.replace(b'@1Chapter 3: Torneko and the Extravagant Excavation@', b'@1Chapter 3: Torneko\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE@')
        patched_data = patched_data.replace(b'@1Chapter 4: Meena and Maya and the Mahabala Mystery@', b'@1Chapter 4: Meena and Maya\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE@')
        patched = True
    return patched_data, patched

def patch_file_en(filename):
    logging.info(f'Patching file {filename}')
    with open(f'en/{filename}', "rb") as in_file, open (f'out/{mode_lang}/{filename}', "wb") as out_file:
        data = in_file.read()
        size = len(data)

        logging.info(f'Size: {size} bytes')

        data, patched = special_case_patch(filename, data)
        if (patched):
            out_file.write(data)
            assert len(data) == size, f"Final size ({len(data)}) does not match original size ({size})"
            logging.info(f'Successfully applied special case patch file en/{filename}')
            return

        final_data = bytearray("", 'utf-8')

        pointer = 0
        segment_start = None
        segment_end = None
        nametag = b''
        while pointer <= size:
            if segment_start == None:
                # Need to look for a new segment start.
                if data[pointer:pointer+2] == b'@a':
                    # Look for the nametag end marker
                    pointer = pointer+2
                    nametag_start = pointer
                    nametag_len = 0
                    while data[pointer:pointer+2] != b'@b':
                        nametag_len += 1
                        pointer += 1
                    nametag = data[nametag_start:nametag_start + nametag_len]

                    # Write the segment start marker
                    final_data.extend(b'@a')
                    if mode_lang == 'en':
                        final_data.extend(nametag)
                    final_data.extend(b'@b')

                    segment_start = pointer+2
                elif pointer < size:
                    # Write any bytes encountered between segments to the output buffer
                    final_data.append(data[pointer])

                pointer += 1
            elif segment_end == None:
                # Need to look for a new segment end.
                if data[pointer:pointer+4] == b'@c3@' or data[pointer:pointer+4] == b'@c2@' or data[pointer:pointer+4] == b'@c1@' or data[pointer:pointer+4] == b'@c0@':
                    segment_end = pointer
                    pointer = pointer+4
                else:
                    pointer += 1
            else:
                # We have a start and end to the segment.
                segment = data[segment_start:segment_end]
                if mode_lang == 'ja' and len(nametag) > 0:
                    # Strip off last char and add nametag*
                    segment_strip_last_char = segment[:len(segment)-1]
                    nametag_part = bytearray(nametag)
                    nametag_part.extend(b'*')
                    segment = nametag_part
                    segment.extend(segment_strip_last_char)
                segmentSize = len(segment)

                nametag_print = f' [{nametag}]' if len(nametag) > 0 else ''
                logging.info(f'Processing segment ({segmentSize} bytes):{nametag_print} {segment}')

                # Process the segment.
                processedSegment = process_segment(filename, segment)
                
                # Write the processed segment.
                final_data.extend(processedSegment)

                # Write the segment end marker
                final_data.extend(data[segment_end:segment_end+4])

                # Reset the segment start/end pointers.
                segment_start = None
                segment_end = None
                nametag = b''

                # break

        out_file.write(final_data)

        assert len(final_data) == size, f"Final size ({len(final_data)}) does not match original size ({size})"

        logging.info(f'Successfully patched file en/{filename}')

def automatic_extract_repack():
    path_to_ndstool = "ndstool"

    # ndstool binary downloads
    ndstool_links = {"linux aarch64" : "https://github.com/fenwaypowers/ndstool/releases/download/2.1.2/ndstool-2.1.2-linux_aarch64.zip",
                     "linux x86_64" : "https://github.com/fenwaypowers/ndstool/releases/download/2.1.2/ndstool-2.1.2-1-linux_x86_64.zip",
                     "mac osx" : "https://github.com/fenwaypowers/ndstool/releases/download/2.1.2/ndstool-2.1.2-1-osx.zip",
                     "win32" : "https://github.com/fenwaypowers/ndstool/releases/download/2.1.2/ndstool-2.1.2-1-win32.zip",
                     "windows" : "https://github.com/fenwaypowers/ndstool/releases/download/2.1.2/ndstool-2.1.2-1-windows.zip",
                     "windows i686" : "https://github.com/fenwaypowers/ndstool/releases/download/2.1.2/ndstool-2.1.2-2-windows_i686.zip",
                     "windows x86_64" : "https://github.com/fenwaypowers/ndstool/releases/download/2.1.2/ndstool-2.1.2-windows_x86_64.zip"}
    
    ndstool_string = "ndstool 2.1.2"

    # Check if ndstool is installed
    ndstool_found = False
    correct_output =  "Nintendo DS rom tool 2.1.2 - Mar  2 2023\\nby Rafael Vuijk, Dave Murphy, Alexei Karpenko"

    ndstool = subprocess.run(path_to_ndstool, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if correct_output in str(ndstool.stdout):
        ndstool_found = True
    else:
        for possible_path in ["ndstool/ndstool", "ndstool/ndstool.exe"]:
            if os.path.exists(possible_path):
                ndstool_found = True
                if possible_path.endswith(".exe"):
                    path_to_ndstool = "ndstool\\ndstool.exe"
                else:
                    path_to_ndstool = possible_path

    # If ndstool isn't found, install
    if not ndstool_found:

        do_not_install_msg = ndstool_string + " is required for automatic rom patching. Use --manual if you wish to do everything manually."
        
        install = input("Could not find " + ndstool_string + " on your system. Download it? (Y/n): ")
        if install in ["", "y", "Y"]:

            dl_list = []
            for i, link in enumerate(ndstool_links):
                print("[" + str(i + 1) + "] " + link)
                dl_list.append(link)

            while(True):
                selection = input("Select a version [1-" + str(len(dl_list)) + "] (n to cancel): ")
                if selection in ["n", "N"]:
                    print(do_not_install_msg)
                    sys.exit(1)

                if selection.isdigit():
                    if int(selection) in range(1,len(dl_list) + 1):
                        break

            selection = int(selection)

            download = requests.get(ndstool_links[dl_list[selection - 1]])

            if not os.path.exists("ndstool"):
                os.makedirs("ndstool")

            with open("ndstool/ndstool.zip",'wb') as f:
                print("Downloading ndstool...")
                f.write(download.content)

                file_to_extract = "ndstool"
                if "win" in dl_list[selection - 1]:
                    file_to_extract += ".exe"
                
                with ZipFile("ndstool/ndstool.zip", 'r') as zObject:
                    zObject.extract(file_to_extract, path="ndstool/")

                print("ndstool downloaded.")


            if file_to_extract.endswith(".exe"):
                path_to_ndstool = "ndstool\\" + file_to_extract
            else:
                path_to_ndstool = "ndstool/" + file_to_extract
                subprocess.run("chmod +x ndstool/ndstool", shell=True)               

        else:
            print(do_not_install_msg)
            sys.exit(1)

    # Check if en folder is missing us nds mpt files
    us_nds_mptlist = ['b0000000.mpt', 'b0001000.mpt', 'b0002000.mpt', 'b0003000.mpt', 'b0004000.mpt', 'b0005000.mpt', 'b0006000.mpt', 'b0007000.mpt', 'b0008000.mpt', 'b0009000.mpt', 'b0010000.mpt', 'b0011000.mpt', 'b0012000.mpt', 'b0014000.mpt', 'b0015000.mpt', 'b0016000.mpt', 'b0017000.mpt', 'b0018000.mpt', 'b0019000.mpt', 'b0025000.mpt', 'b0026000.mpt', 'b0027000.mpt', 'b0028000.mpt', 'b0029000.mpt', 'b0030000.mpt', 'b0031000.mpt', 'b0032000.mpt', 'b0033000.mpt', 'b0034000.mpt', 'b0035000.mpt', 'b0037000.mpt', 'b0038000.mpt', 'b0039000.mpt', 'b0040000.mpt', 'b0045000.mpt', 'b0046000.mpt', 'b0047000.mpt', 'b0049000.mpt', 'b0050000.mpt', 'b0051000.mpt', 'b0053000.mpt', 'b0054000.mpt', 'b0055000.mpt', 'b0065000.mpt', 'b0066000.mpt', 'b0067000.mpt', 'b0069000.mpt', 'b0070000.mpt', 'b0071000.mpt', 'b0072000.mpt', 'b0073000.mpt', 'b0075000.mpt', 'b0076000.mpt', 'b0077000.mpt', 'b0079000.mpt', 'b0080000.mpt', 'b0081000.mpt', 'b0082000.mpt', 'b0083000.mpt', 'b0084000.mpt', 'b0085000.mpt', 'b0086000.mpt', 'b0087000.mpt', 'b0088000.mpt', 'b0090000.mpt', 'b0091000.mpt', 'b0093000.mpt', 'b0094000.mpt', 'b0095000.mpt', 'b0096000.mpt', 'b0097000.mpt', 'b0098000.mpt', 'b0099000.mpt', 'b0100000.mpt', 'b0101000.mpt', 'b0102000.mpt', 'b0103000.mpt', 'b0104000.mpt', 'b0105000.mpt', 'b0106000.mpt', 'b0107000.mpt', 'b0109000.mpt', 'b0110000.mpt', 'b0112000.mpt', 'b0113000.mpt', 'b0115000.mpt', 'b0116000.mpt', 'b0118000.mpt', 'b0119000.mpt', 'b0120000.mpt', 'b0121000.mpt', 'b0122000.mpt', 'b0123000.mpt', 'b0124000.mpt', 'b0125000.mpt', 'b0126000.mpt', 'b0127000.mpt', 'b0128000.mpt', 'b0129000.mpt', 'b0130000.mpt', 'b0145000.mpt', 'b0146000.mpt', 'b0148000.mpt', 'b0149000.mpt', 'b0150000.mpt', 'b0151000.mpt', 'b0152000.mpt', 'b0153000.mpt', 'b0154000.mpt', 'b0155000.mpt', 'b0156000.mpt', 'b0157000.mpt', 'b0200000.mpt', 'b0600000.mpt', 'b0601000.mpt', 'b0602000.mpt', 'b0606000.mpt', 'b0801000.mpt', 'b0802000.mpt', 'b0803000.mpt', 'b0804000.mpt', 'b0805000.mpt', 'b0806000.mpt', 'b0807000.mpt', 'b0808000.mpt', 'b0810000.mpt', 'b0811000.mpt', 'b0812000.mpt', 'b0813000.mpt', 'b0814000.mpt', 'b0815000.mpt', 'b0816000.mpt', 'b0820000.mpt', 'b0821000.mpt', 'b0822000.mpt', 'b0823000.mpt', 'b0824000.mpt', 'b0825000.mpt', 'b0830000.mpt', 'b0831000.mpt', 'b0832000.mpt', 'b0833000.mpt', 'b0834000.mpt', 'b0901000.mpt', 'b1000000.mpt', 'b1001000.mpt', 'b1002000.mpt', 'b1003000.mpt', 'b1004000.mpt', 'b1005000.mpt', 'b1006000.mpt', 'b1007000.mpt', 'b1010000.mpt']
    move_mpt_files = False
    for nds_mpt in us_nds_mptlist:
        if not os.path.exists("en/" + nds_mpt):
            move_mpt_files = True
    
    path_to_us_nds_files = "roms/" + "us" + "/data/data/MESS/en"

    # Check if US rom needs to be extraced
    extract_us_rom = False
    for nds_mpt in us_nds_mptlist:
        if not os.path.exists(path_to_us_nds_files + "/" + nds_mpt):
            extract_us_rom = True
    
    # Extract JA and possibly US rom
    extract_roms(path_to_ndstool, extract_us_rom)

    # Move US NDS mpt files from extracted folder to en
    if move_mpt_files:
        move_nds_mpt()
    
    # Check if obb mpt files need to be extraced
    obb_mpt_list = ['assets/msg/en/b0500000.mpt', 'assets/msg/en/b0501000.mpt', 'assets/msg/en/b0502000.mpt', 'assets/msg/en/b0503000.mpt', 'assets/msg/en/b0504000.mpt', 'assets/msg/en/b0505000.mpt', 'assets/msg/en/b0506000.mpt', 'assets/msg/en/b0507000.mpt', 'assets/msg/en/b0508000.mpt', 'assets/msg/en/b0509000.mpt', 'assets/msg/en/b0512000.mpt', 'assets/msg/en/b0513000.mpt', 'assets/msg/en/b0516000.mpt', 'assets/msg/en/b0517000.mpt', 'assets/msg/en/b0520000.mpt', 'assets/msg/en/b0521000.mpt', 'assets/msg/en/b0522000.mpt', 'assets/msg/en/b0523000.mpt', 'assets/msg/en/b0524000.mpt', 'assets/msg/en/b0525000.mpt', 'assets/msg/en/b0526000.mpt', 'assets/msg/en/b0527000.mpt', 'assets/msg/en/b0528000.mpt',
            'assets/msg/en/b0529000.mpt', 'assets/msg/en/b0530000.mpt', 'assets/msg/en/b0531000.mpt', 'assets/msg/en/b0532000.mpt', 'assets/msg/en/b0533000.mpt', 'assets/msg/en/b0534000.mpt', 'assets/msg/en/b0535000.mpt', 'assets/msg/en/b0536000.mpt', 'assets/msg/en/b0537000.mpt', 'assets/msg/en/b0538000.mpt', 'assets/msg/en/b0539000.mpt', 'assets/msg/en/b0540000.mpt', 'assets/msg/en/b0541000.mpt', 'assets/msg/en/b0542000.mpt', 'assets/msg/en/b0543000.mpt', 'assets/msg/en/b0544000.mpt', 'assets/msg/en/b0545000.mpt', 'assets/msg/en/b0547000.mpt', 'assets/msg/en/b0548000.mpt', 'assets/msg/en/b0549000.mpt', 'assets/msg/en/b0550000.mpt', 'assets/msg/en/b0551000.mpt', 'assets/msg/en/b0552000.mpt']
    extract_obb_ = False
    for obb in obb_mpt_list:
        if not os.path.exists(obb.split("assets/msg/")[1]):
            extract_obb_ = True
    
    # Extract the obb mpt files
    if extract_obb_:
        extract_obb()

    return path_to_ndstool

def extract_roms(path_to_ndstool: str, extract_us: bool):
    regions = []
    roms = {"us" : "none",
            "ja" : "none"}

    for r in os.listdir("roms"):
        if r.endswith(".nds"):
            rom = subprocess.run(path_to_ndstool + " -i " + path_to_roms + "/" + r, shell=True, stdout=subprocess.PIPE)

            if "YIVE (NTR-YIVE-USA)" in str(rom.stdout) and extract_us:
                roms["us"] = path_to_roms + "/" + r
            elif "YIVJ (NTR-YIVJ-JPN)" in str(rom.stdout):
                roms["ja"] = path_to_roms + "/" + r

    if roms["us"] == "none" and extract_us:
        print("Please provide a US DQIV rom in the roms folder.")
        sys.exit(1)
    
    if roms["us"] != "none":
        regions.append("us")

    if roms["ja"] == "none":
        print("Please provide a JA DQIV rom in the roms folder.")
        sys.exit(1)
    else:
        regions.append("ja")
    
    # Extract JA/US roms
    for region in regions:
        path_to_region_folder = path_to_roms + "/" + region
        if not os.path.exists(path_to_region_folder):
            os.makedirs(path_to_region_folder)

        print("Extracting " + region + " rom...")
        subprocess.run(path_to_ndstool + " -x " + roms[region] + " -9 " + path_to_region_folder + "/arm9.bin -7 " + path_to_region_folder + "/arm7.bin -y9 " + path_to_region_folder + "/y9.bin -y7 " + path_to_region_folder + "/y7.bin -t " + path_to_region_folder + "/banner.bin -h " + path_to_region_folder + "/header.bin -d " + path_to_region_folder + "/data -y " + path_to_region_folder + "/overlay ", shell=True, stdout=subprocess.PIPE)
        print("Extraction of " + region + " rom complete.")
    
def move_nds_mpt():
    # Copy the US NDS mpt files to en
    path_to_en_ds_files = path_to_roms + "/" + "us" + "/data/data/MESS/en"
    for f in os.listdir(path_to_en_ds_files):
        try:
            shutil.copy(path_to_en_ds_files + "/" + f, "en/" + f)
        except:
            print("File en/" + f + " already exists. Skipping copying the file.")

def extract_obb():
    obb = "none"

    # Locate the US and JA NDS roms as well as obb file
    for r in os.listdir("roms"):
        if r.endswith(".obb"):
            obb = r

    # Check if obb exists
    if obb == "none":
        print("Please provide a DQIV android .obb file in the roms folder.")
        sys.exit(1)

    # List of mpts to extract from the obb
    mpt_list = ['assets/msg/en/b0500000.mpt', 'assets/msg/en/b0501000.mpt', 'assets/msg/en/b0502000.mpt', 'assets/msg/en/b0503000.mpt', 'assets/msg/en/b0504000.mpt', 'assets/msg/en/b0505000.mpt', 'assets/msg/en/b0506000.mpt', 'assets/msg/en/b0507000.mpt', 'assets/msg/en/b0508000.mpt', 'assets/msg/en/b0509000.mpt', 'assets/msg/en/b0512000.mpt', 'assets/msg/en/b0513000.mpt', 'assets/msg/en/b0516000.mpt', 'assets/msg/en/b0517000.mpt', 'assets/msg/en/b0520000.mpt', 'assets/msg/en/b0521000.mpt', 'assets/msg/en/b0522000.mpt', 'assets/msg/en/b0523000.mpt', 'assets/msg/en/b0524000.mpt', 'assets/msg/en/b0525000.mpt', 'assets/msg/en/b0526000.mpt', 'assets/msg/en/b0527000.mpt', 'assets/msg/en/b0528000.mpt',
            'assets/msg/en/b0529000.mpt', 'assets/msg/en/b0530000.mpt', 'assets/msg/en/b0531000.mpt', 'assets/msg/en/b0532000.mpt', 'assets/msg/en/b0533000.mpt', 'assets/msg/en/b0534000.mpt', 'assets/msg/en/b0535000.mpt', 'assets/msg/en/b0536000.mpt', 'assets/msg/en/b0537000.mpt', 'assets/msg/en/b0538000.mpt', 'assets/msg/en/b0539000.mpt', 'assets/msg/en/b0540000.mpt', 'assets/msg/en/b0541000.mpt', 'assets/msg/en/b0542000.mpt', 'assets/msg/en/b0543000.mpt', 'assets/msg/en/b0544000.mpt', 'assets/msg/en/b0545000.mpt', 'assets/msg/en/b0547000.mpt', 'assets/msg/en/b0548000.mpt', 'assets/msg/en/b0549000.mpt', 'assets/msg/en/b0550000.mpt', 'assets/msg/en/b0551000.mpt', 'assets/msg/en/b0552000.mpt']
    
    # Extract the files and move the extracted files to root of en folder
    print("Extracting files from obb...")
    for mpt in mpt_list:
        with ZipFile(path_to_roms + "/" + obb, 'r') as zObject:
            zObject.extract(mpt, path="en/")
            try:
                os.rename("en/" + mpt, "en/" + mpt.split("assets/msg/en/")[1])
            except:
                print("File en/" + mpt + "already exists. Skipping copying the file...")
    print("Extraction of obb files complete.")
    shutil.rmtree("en/assets")

def repack(mode_lang: str, mode_gender: str, path_to_ndstool: str):
    
    # Define path where mpt files will be replaced
    path = path_to_roms + "/" + "repack" + "/data/data/MESS/" + mode_lang

    # Remove repack folder if it exists
    if os.path.exists(path_to_roms + "/repack"):
        shutil.rmtree(path_to_roms + "/repack")

    # Create a copy of the extracted JA NDS rom folder called repack
    shutil.copytree(path_to_roms + "/" + "ja", path_to_roms + "/" + "repack")
    path_to_repack = path_to_roms + "/" + "repack"

    # Remove all mpt's from path and move the mpt files in out to path
    for i in os.listdir(path):
        os.remove(path + "/" + i)
    for j in os.listdir("out/" + mode_lang):
        os.rename("out/" + mode_lang + "/" + j, path + "/" + j)

    path_to_repack = path_to_roms + "/" + "repack"

    if not os.path.exists("patched"):
        os.mkdir("patched")

    # Repack the rom with ndstool
    print("Repacking rom...")
    repacking = subprocess.run(path_to_ndstool + " -c \"patched/" + "Dragon Quest IV Party Chat Patched [" + "yuusha=" + mode_yuusha + " gender=" + mode_gender + " lang=" + mode_lang + "].nds\"" + " -9 " + path_to_repack + "/arm9.bin -7 " + path_to_repack + "/arm7.bin -y9 " + path_to_repack + "/y9.bin -y7 " +
                   path_to_repack + "/y7.bin -t " + path_to_repack + "/banner.bin -h " + path_to_repack + "/header.bin -d " + path_to_repack + "/data -y " + path_to_repack + "/overlay ", shell=True, stdout=subprocess.PIPE)
    print("Rom repacked!")

    # Remove the repack folder
    shutil.rmtree(path_to_repack)

    # Remove the ndstool zip
    if os.path.exists("ndstool/ndstool.zip"):
        os.remove("ndstool/ndstool.zip")

if __name__ == "__main__":
    main()
