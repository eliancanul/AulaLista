"""Small dependency-free QR encoder for the local access page.

This is intentionally limited to byte-mode QR codes with low error correction
and versions 1 through 5. A LAN URL is short enough for that range, and keeping
the encoder in the project means the access page has no runtime CDN or package
requirement.
"""

from html import escape


_ECC_CODEWORDS_PER_BLOCK = (7, 10, 15, 20, 26)
_NUM_ERROR_CORRECTION_BLOCKS = (1, 1, 1, 1, 1)
_DATA_CODEWORDS = (19, 34, 55, 80, 108)
_ALIGNMENT_POSITIONS = ((), (6, 18), (6, 22), (6, 26), (6, 30))


def _gf_multiply(x, y):
    result = 0
    while y:
        if y & 1:
            result ^= x
        y >>= 1
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    return result


def _reed_solomon_generator(degree):
    generator = [1]
    factor = 1
    for _ in range(degree):
        next_generator = [0] * (len(generator) + 1)
        for position, coefficient in enumerate(generator):
            next_generator[position] ^= coefficient
            next_generator[position + 1] ^= _gf_multiply(coefficient, factor)
        generator = next_generator
        factor = _gf_multiply(factor, 2)
    return generator


def _reed_solomon_remainder(data, degree):
    generator = _reed_solomon_generator(degree)

    remainder = [0] * degree
    for value in data:
        factor = value ^ remainder[0]
        remainder = remainder[1:] + [0]
        for position in range(degree):
            remainder[position] ^= _gf_multiply(generator[position + 1], factor)
    return remainder


def _append_bits(bits, value, length):
    bits.extend((value >> index) & 1 for index in range(length - 1, -1, -1))


def _data_codewords(text, version):
    payload = text.encode("utf-8")
    capacity = _DATA_CODEWORDS[version - 1] * 8
    bits = []
    _append_bits(bits, 0b0100, 4)  # byte mode
    _append_bits(bits, len(payload), 8)
    for value in payload:
        _append_bits(bits, value, 8)
    if len(bits) > capacity:
        raise ValueError("La URL local es demasiado larga para el QR local.")
    _append_bits(bits, 0, min(4, capacity - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    codewords = [
        sum(bits[index + offset] << (7 - offset) for offset in range(8))
        for index in range(0, len(bits), 8)
    ]
    padding = (0xEC, 0x11)
    position = 0
    while len(codewords) < _DATA_CODEWORDS[version - 1]:
        codewords.append(padding[position % 2])
        position += 1
    return codewords


def _interleave_codewords(data, version):
    block_count = _NUM_ERROR_CORRECTION_BLOCKS[version - 1]
    ecc_length = _ECC_CODEWORDS_PER_BLOCK[version - 1]
    block_data_length = len(data) // block_count
    data_blocks = [
        data[index * block_data_length : (index + 1) * block_data_length]
        for index in range(block_count)
    ]
    ecc_blocks = [
        _reed_solomon_remainder(block, ecc_length) for block in data_blocks
    ]
    return [
        value
        for position in range(max(map(len, data_blocks)))
        for block in data_blocks
        if position < len(block)
        for value in (block[position],)
    ] + [
        value
        for position in range(ecc_length)
        for block in ecc_blocks
        for value in (block[position],)
    ]


def _finder_pattern(matrix, row, column):
    size = len(matrix)
    for row_offset in range(-4, 5):
        for column_offset in range(-4, 5):
            current_row = row + row_offset
            current_column = column + column_offset
            if not (0 <= current_row < size and 0 <= current_column < size):
                continue
            distance = max(abs(row_offset), abs(column_offset))
            matrix[current_row][current_column] = distance in (0, 1, 3)


def _draw_function_patterns(matrix, version):
    size = len(matrix)
    _finder_pattern(matrix, 3, 3)
    _finder_pattern(matrix, 3, size - 4)
    _finder_pattern(matrix, size - 4, 3)

    for row in range(6, size - 6):
        if matrix[row][6] is None:
            matrix[row][6] = row % 2 == 0
    for column in range(6, size - 6):
        if matrix[6][column] is None:
            matrix[6][column] = column % 2 == 0

    for row in _ALIGNMENT_POSITIONS[version - 1]:
        for column in _ALIGNMENT_POSITIONS[version - 1]:
            if matrix[row][column] is not None:
                continue
            for row_offset in range(-2, 3):
                for column_offset in range(-2, 3):
                    matrix[row + row_offset][column + column_offset] = (
                        max(abs(row_offset), abs(column_offset)) != 1
                    )

    matrix[size - 8][8] = True


def _format_bits(mask):
    value = (1 << 3) | mask  # error correction level L
    value = (value << 10) | _bch_remainder(value, 0x537)
    return value ^ 0x5412


def _bch_remainder(value, polynomial):
    degree = polynomial.bit_length() - 1
    value <<= degree
    while value.bit_length() >= polynomial.bit_length():
        value ^= polynomial << (value.bit_length() - polynomial.bit_length())
    return value


def _draw_format_bits(matrix, mask):
    size = len(matrix)
    bits = _format_bits(mask)
    for index in range(15):
        value = bool((bits >> index) & 1)
        if index < 6:
            matrix[index][8] = value
        elif index < 8:
            matrix[index + 1][8] = value
        else:
            matrix[size - 15 + index][8] = value

        if index < 8:
            matrix[8][size - index - 1] = value
        elif index < 9:
            matrix[8][15 - index] = value
        else:
            matrix[8][15 - index - 1] = value
    matrix[size - 8][8] = True


def _mask_applies(mask, row, column):
    if mask == 0:
        return (row + column) % 2 == 0
    if mask == 1:
        return row % 2 == 0
    if mask == 2:
        return column % 3 == 0
    if mask == 3:
        return (row + column) % 3 == 0
    if mask == 4:
        return (row // 2 + column // 3) % 2 == 0
    if mask == 5:
        return row * column % 2 + row * column % 3 == 0
    if mask == 6:
        return (row * column % 2 + row * column % 3) % 2 == 0
    return ((row + column) % 2 + row * column % 3) % 2 == 0


def _draw_codewords(matrix, codewords, mask):
    size = len(matrix)
    bits = [
        (value >> bit) & 1
        for value in codewords
        for bit in range(7, -1, -1)
    ]
    bit_position = 0
    column = size - 1
    upward = True
    while column > 0:
        if column == 6:
            column -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for current_column in (column, column - 1):
                if matrix[row][current_column] is not None:
                    continue
                value = bits[bit_position] if bit_position < len(bits) else 0
                bit_position += 1
                matrix[row][current_column] = bool(value) ^ _mask_applies(
                    mask, row, current_column
                )
        upward = not upward
        column -= 2


def _penalty(matrix):
    size = len(matrix)
    score = 0
    for row in matrix:
        for offset in range(size - 4):
            if len(set(row[offset : offset + 5])) == 1:
                score += 3
            if offset <= size - 7 and len(set(row[offset : offset + 7])) == 1:
                score += 40
    for column in range(size):
        values = [matrix[row][column] for row in range(size)]
        for offset in range(size - 4):
            if len(set(values[offset : offset + 5])) == 1:
                score += 3
            if offset <= size - 7 and len(set(values[offset : offset + 7])) == 1:
                score += 40
    for row in range(size - 1):
        for column in range(size - 1):
            if matrix[row][column] == matrix[row + 1][column] == matrix[row][column + 1] == matrix[row + 1][column + 1]:
                score += 3
    dark = sum(value for row in matrix for value in row)
    score += abs(dark * 20 - size * size * 10) // (size * size) * 10
    return score


def qr_matrix(text):
    payload = text.encode("utf-8")
    version = next(
        (
            number
            for number, codeword_count in enumerate(_DATA_CODEWORDS, start=1)
            if 12 + len(payload) * 8 <= codeword_count * 8
        ),
        None,
    )
    if version is None:
        raise ValueError("La URL local es demasiado larga para el QR local.")
    codewords = _interleave_codewords(_data_codewords(text, version), version)
    candidates = []
    for mask in range(8):
        matrix = [[None] * (version * 4 + 17) for _ in range(version * 4 + 17)]
        _draw_function_patterns(matrix, version)
        _draw_codewords(matrix, codewords, mask)
        _draw_format_bits(matrix, mask)
        candidates.append((_penalty(matrix), matrix))
    return min(candidates, key=lambda item: item[0])[1]


def qr_svg(text, border=4, module_size=6):
    matrix = qr_matrix(text)
    size = len(matrix)
    dimension = (size + border * 2) * module_size
    paths = []
    for row, values in enumerate(matrix):
        for column, value in enumerate(values):
            if value:
                paths.append(
                    f"M{(column + border) * module_size} {(row + border) * module_size}"
                    f"h{module_size}v{module_size}h-{module_size}z"
                )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Código QR para {escape(text)}" viewBox="0 0 {dimension} {dimension}" '
        f'width="{dimension}" height="{dimension}" data-qr-value="{escape(text)}">'
        f'<rect width="100%" height="100%" fill="white"/><path fill="black" d="{"".join(paths)}"/>'
        "</svg>"
    )
