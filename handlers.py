from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from Connection import Connection
from State import SearchState, BuyBookState, ReplenishBalanceState
from keyboard import *

router = Router()
search_state = SearchState()
balance_state = ReplenishBalanceState()
db = Connection()


@router.message(F.text == '/start')
async def start(message: Message):
    """Первые слова бота после /start."""
    db.add_user(message.from_user.id, message.from_user.username, message.chat.id)
    await message.answer(
        'Привет. Этот бот предназначен для поиска и бронирования книг в нашей библиотеке.\n'
        'Пиши /request для поиска книги в библиотеке.\n'
        f'Искать можно по <b>названию</b>, <b>автору</b> и <b>артикулу</b>',
        parse_mode="HTML"
    )


@router.message(F.text == '/request')
async def search(message: Message, state: FSMContext):
    """Запрос на поиск книги по критериям."""
    await message.answer(
        text='Введите поисковый запрос.\nВ дальнейшем вы сможете выбрать тип поиска'
    )
    await state.set_state(search_state.WAITING_FOR_SEARCH_QUERY)


@router.message(F.text == '/my_orders')
async def user_orders(message: Message):
    """Список книг у пользователя в корзине."""
    books = db.cursor.execute(
        "SELECT bookName,"
        " bookAuthor,"
        " bookGenre,"
        " bookPrice,"
        " bookCount,"
        " bookVendor FROM selected_books WHERE userID = (?)",
        (message.from_user.id,)
    ).fetchall()
    if books is None:
        await message.answer(
            'У вас нет книг в корзине. Пишите /request, чтобы найти книгу'
        )
    else:
        for book in books:
            book_name = book[0]
            book_author = book[1]
            book_genre = book[2]
            book_price = book[3]
            book_count = book[4]
            book_vendor = book[5]

            await message.answer(
                text=f'Название: {book_name}\nАвтор: {book_author}\nЖанр: {book_genre}\nЦена: {book_price}'
                     f'\nКоличество: {book_count}\n'
                     f'Артикул: `{book_vendor}`',
                reply_markup=get_delete_keyboard(book_vendor), parse_mode='MARKDOWN'
            )
        final_price = db.get_whole_price(message.from_user.id)
        await message.answer(
            text=f'Ваш баланс <b>{db.get_balance(message.from_user.id)}</b>'
                 f'\nОбщая стоимость вашей корзины: {final_price}',
            reply_markup=get_pay_for_books_keyboard(),
            parse_mode='HTML'
        )


@router.callback_query(F.data == 'pay')
async def pay_for_books(callback: CallbackQuery):
    """Оплата за книги."""
    final_price = db.get_whole_price(callback.from_user.id)
    if db.get_balance(callback.from_user.id) - final_price >= 0:
        db.pay_whole_price(callback.from_user.id, final_price)
        await callback.answer(text='Успешно оплачено!', show_alert=True)
        await callback.bot.delete_message(
            chat_id=callback.message.chat.id, message_id=callback.message.message_id
        )
    else:
        await callback.answer(text='На балансе недостаточно денег.', show_alert=True)


@router.message(F.text == '/balance')
async def get_balance(message: Message):
    """Просмотр баланса."""
    balance = db.get_balance(message.from_user.id)
    await message.answer(
        text="<b>Данная функция предназначена в учебных целях. Она никак не пополнит ваш счёт.</b>"
             f"\nВаш баланс: {balance}", reply_markup=get_balance_keyboard(),
        parse_mode='HTML'
    )


@router.callback_query(F.data == 'replenish')
async def replenish_balance(callback: CallbackQuery, state: FSMContext):
    """Пополнение баланса."""
    await callback.message.answer(text='Введите сумму на которую нужно пополнить баланс')
    await state.set_state(balance_state.WAIT_FOR_SUM)
    await callback.answer()


@router.message(balance_state.WAIT_FOR_SUM)
async def update_balance(message: Message, state: FSMContext):
    """Успешное пополнение."""
    db.update_balance(float(message.text), message.from_user.id)
    await message.answer(
        text=f'Баланс успешно пополнен на сумму: <b>{message.text}</b>', parse_mode='HTML'
    )
    await state.clear()


@router.message(search_state.WAITING_FOR_SEARCH_QUERY)
async def choice_search_category(message: Message, state: FSMContext):
    """Выбор критерия поиска."""
    await message.answer(
        'Выберите категорию поиска', reply_markup=get_search_choice_keyboard()
    )
    await state.update_data(search_request=message.text)


@router.callback_query(F.data == 'book_name')  # TITLE
async def search_by_title(callback: CallbackQuery, state: FSMContext):
    """Поиск по названию книги."""
    search_query = await state.get_data()
    book = db.cursor.execute(
        "SELECT bookName, authorBook, bookGenre, bookPrice, bookCount, bookVendor FROM books WHERE bookName = (?)",
        (search_query['search_request'],)
    ).fetchone()

    if book is None:
        await callback.message.answer(
            text=f'Книг с названием <b>{search_query["search_request"]}</b> в магазине нет.',
            parse_mode="HTML"
        )
    else:
        title = book[0]
        author = book[1]
        genre = book[2]
        price = book[3]
        count = book[4]
        vendor = book[5]
        await callback.message.answer(
            text=f'Книга с названием "{title}" найдена.\n{author}\nЦена: {price}\nОстаток на складе: {count}'
                 f'\nАртикул: `{vendor}`',
            reply_markup=get_buy_book_keyboard(book_vendor=vendor),
            parse_mode="MARKDOWN"
        )
    await callback.answer()


@router.callback_query(F.data == 'book_author')  # AUTHOR
async def search_by_author(callback: CallbackQuery, state: FSMContext):
    """Поиск по автору книги."""
    search_query = await state.get_data()
    books = db.cursor.execute(
        "SELECT bookName, authorBook, bookGenre, bookPrice, bookCount, bookVendor FROM books WHERE authorBook LIKE ?",
        (search_query['search_request'] + '%',)
    ).fetchall()

    if books is None:
        await callback.message.answer(
            text=f'Книг автора {search_query["search_request"]} в магазине нет.'
        )
    else:
        for book in books:
            title = book[0]
            author = book[1]
            genre = book[2]
            price = book[3]
            count = book[4]
            vendor = book[5]

            await state.set_state(BuyBookState.BOOK_INFO)
            await state.update_data(
                book_name=title,
                book_author=author,
                book_genre=genre,
                book_price=price,
                book_count=count,
                book_vendor=vendor
            )
            data = await state.get_data()
            vendor = data['book_vendor']

            await callback.message.answer(
                text=f'Книга с названием "{title}" найдена.\n{author} Жанр книги: {genre}\nЦена: {price}\n'
                     f'Остаток на складе: {count}'
                     f'\nАртикул: `{vendor}`',
                reply_markup=get_buy_book_keyboard(book_vendor=vendor),
                parse_mode="MARKDOWN"
            )
    await callback.answer()


@router.callback_query(F.data == 'book_vendor')  # VENDOR
async def search_by_vendor(callback: CallbackQuery, state: FSMContext):
    """Поиск по артикулу книги."""
    search_query = await state.get_data()
    book = db.cursor.execute(
        "SELECT bookName, authorBook, bookGenre, bookPrice, bookCount, bookVendor FROM books WHERE bookVendor = (?)",
        (search_query['search_request'],)
    ).fetchone()

    if book is None:
        await callback.message.answer(
            text=f'Книги c артикулом {search_query["search_request"]} в магазине нет.'
        )
    else:
        title = book[0]
        author = book[1]
        genre = book[2]
        price = book[3]
        count = book[4]
        vendor = book[5]
        await callback.message.answer(
            text=f'Книга "{title}" найдена .\n{author}\nЦена: {price}\nОстаток на складе: {count}'
                 f'\nАртикул: `{vendor}`',
            reply_markup=get_buy_book_keyboard(book_vendor=vendor),
            parse_mode="MARKDOWN"
        )
        await callback.answer()


@router.callback_query(lambda f: f.data.startswith('request_for_count:'))
async def request_for_count(callback: CallbackQuery):
    """Выбор количества книг в корзину."""
    vendor = callback.data.split(':')[-1]
    book = db.cursor.execute(
        "SELECT bookName, authorBook, bookGenre, bookPrice, bookCount, bookVendor FROM books WHERE bookVendor = (?)",
        (vendor,)
    ).fetchone()
    max_count = book[4]

    await callback.message.answer(
        text=f'Выберите количество. Максимальное: {max_count}\nТекущее: 1',
        reply_markup=get_count_book_keyboard(vendor)
    )

    await callback.answer()


@router.callback_query(lambda f: f.data.startswith('plus:'))
async def plus_one_callback(callback: CallbackQuery):
    """Добавление 1 книги."""
    current_number = int(callback.message.text.split(": ")[-1])
    vendor = callback.data.split(':')[-1]

    book = db.cursor.execute(
        "SELECT bookName, authorBook, bookGenre, bookPrice, bookCount, bookVendor FROM books WHERE bookVendor = (?)",
        (vendor,)
    ).fetchone()
    max_count = book[4]

    if current_number == max_count:
        pass
    else:
        current_number += 1
        await callback.message.edit_text(
            text=f'Выберите количество. Максимальное: {max_count}\nТекущее: {current_number}',
            reply_markup=get_count_book_keyboard(vendor)
        )

    await callback.answer()


@router.callback_query(lambda f: f.data.startswith('plus5:'))
async def plus_five_callback(callback: CallbackQuery):
    """Добавление 5 книг."""
    current_number = int(callback.message.text.split(": ")[-1])
    vendor = callback.data.split(':')[-1]

    book = db.cursor.execute(
        "SELECT bookName, authorBook, bookGenre, bookPrice, bookCount, bookVendor FROM books WHERE bookVendor = (?)",
        (vendor,)
    ).fetchone()
    max_count = book[4]

    if current_number + 5 > max_count:
        pass
    else:
        current_number += 5
        await callback.message.edit_text(
            text=f'Выберите количество. Максимальное: {max_count}\nТекущее: {current_number}',
            reply_markup=get_count_book_keyboard(vendor)
        )

    await callback.answer()


@router.callback_query(lambda f: f.data.startswith('minus:'))
async def minus_one_callback(callback: CallbackQuery):
    """Убрать ону книгу."""
    current_number = int(callback.message.text.split(": ")[-1])
    vendor = callback.data.split(':')[-1]

    book = db.cursor.execute(
        "SELECT bookName, authorBook, bookGenre, bookPrice, bookCount, bookVendor FROM books WHERE bookVendor = (?)",
        (vendor,)
    ).fetchone()
    max_count = book[4]

    if current_number == 1:
        pass
    else:
        current_number -= 1
        await callback.message.edit_text(
            text=f'Выберите количество. Максимальное: {max_count}\nТекущее: {current_number}',
            reply_markup=get_count_book_keyboard(vendor)
        )

    await callback.answer()


@router.callback_query(lambda f: f.data.startswith('minus5:'))
async def minus_five_callback(callback: CallbackQuery):
    """Убрать 5 книг."""
    current_number = int(callback.message.text.split(": ")[-1])
    vendor = callback.data.split(':')[-1]

    book = db.cursor.execute(
        "SELECT bookName, authorBook, bookGenre, bookPrice, bookCount, bookVendor FROM books WHERE bookVendor = (?)",
        (vendor,)
    ).fetchone()
    max_count = book[4]

    if current_number <= 5:
        pass
    else:
        current_number -= 5
        await callback.message.edit_text(
            text=f'Выберите количество. Максимальное: {max_count}\nТекущее: {current_number}',
            reply_markup=get_count_book_keyboard(vendor)
        )

    await callback.answer()


@router.callback_query(lambda f: f.data.startswith('confirm:'))
async def to_chip_basket(callback: CallbackQuery, state: FSMContext):
    """Подтвердить добавление книг в корзину."""
    vendor = callback.data.split(':')[-1]

    book = db.cursor.execute(
        "SELECT bookName, authorBook, bookGenre, bookPrice, bookCount, bookVendor FROM books WHERE bookVendor = (?)",
        (vendor,)
    ).fetchone()
    count_of_books_on_stock = book[4]

    user_id = callback.from_user.id
    book_name = book[0]
    book_author = book[1]
    book_genre = book[2]
    book_price = book[3]
    book_count = int(callback.message.text.split(": ")[-1])

    db.cursor.execute(
        "INSERT INTO selected_books (userID, bookName, bookAuthor, bookGenre, bookCount, bookPrice, bookVendor) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, book_name, book_author, book_genre, book_count, book_price, vendor,)
    )
    db.cursor.execute(
        'UPDATE books SET bookCount = ? WHERE bookVendor = ?',
        (count_of_books_on_stock - book_count, vendor,)
    )
    db.connection.commit()

    await callback.message.answer(f'Книга "{book_name}" забронирована.')
    await state.set_state(BuyBookState.BOOK_INFO)
    await callback.answer()


@router.callback_query(lambda f: f.data.startswith('remove:'))
async def remove_from_orders(callback: CallbackQuery, bot: Bot):
    """Убрать из выбора."""
    vendor = callback.data.split(':')[-1]
    db.cursor.execute("DELETE FROM selected_books WHERE bookVendor = (?)", (vendor,))
    db.connection.commit()

    await bot.delete_message(
        chat_id=callback.from_user.id, message_id=callback.message.message_id
    )
    await callback.answer(text='Успешно убрано', show_alert=True)
