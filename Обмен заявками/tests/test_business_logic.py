from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    Branch,
    DeliverySessionLine,
    DemandLine,
    DemandStatus,
    Item,
    Request,
    RequestLine,
    User,
    UserRole,
)
from app.routers.admin.demand import _adjust_active_demand
from app.routers.admin._helpers import _request_has_delivery
from app.schemas import DeliveryLineInput, RequestLineInput
from app.services.delivery_service import (
    DeliveryValidationError,
    close_delivery_session,
    get_or_open_delivery_session,
    save_delivery_result,
)
from app.services.request_service import create_request
from app.services.request_service import RequestValidationError


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSession()

    branch = Branch(name="Ломбард №005", address="Тестовый адрес")
    appraiser = User(full_name="Товаровед", role=UserRole.appraiser)
    driver = User(full_name="Водитель", role=UserRole.driver)
    packages = Item(name="Пакеты", unit="шт.")
    paper = Item(name="Бумага А4", unit="пачка")
    pens = Item(name="Ручки", unit="шт.")
    db.add_all([branch, appraiser, driver, packages, paper, pens])
    db.flush()
    appraiser.branch_id = branch.id
    db.commit()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def _ids(db):
    return {
        "branch": db.query(Branch).filter_by(name="Ломбард №005").one().id,
        "appraiser": db.query(User).filter_by(role=UserRole.appraiser).one().id,
        "driver": db.query(User).filter_by(role=UserRole.driver).one().id,
        "packages": db.query(Item).filter_by(name="Пакеты").one().id,
        "paper": db.query(Item).filter_by(name="Бумага А4").one().id,
        "pens": db.query(Item).filter_by(name="Ручки").one().id,
    }


def test_request_creates_active_demand(db_session):
    ids = _ids(db_session)

    request = create_request(
        db_session,
        ids["appraiser"],
        ids["branch"],
        "Первая заявка",
        [RequestLineInput(item_id=ids["packages"], qty_requested=20)],
    )

    demand = db_session.query(DemandLine).one()
    assert request.status.value == "processed"
    assert demand.branch_id == ids["branch"]
    assert demand.item_id == ids["packages"]
    assert float(demand.qty_total_requested) == 20
    assert float(demand.qty_total_delivered) == 0
    assert float(demand.qty_remaining) == 20
    assert demand.status == DemandStatus.active


def test_request_quantity_allows_decimal(db_session):
    ids = _ids(db_session)

    create_request(
        db_session,
        ids["appraiser"],
        ids["branch"],
        None,
        [RequestLineInput(item_id=ids["packages"], qty_requested=1.5)],
    )

    demand = db_session.query(DemandLine).one()
    assert float(demand.qty_total_requested) == 1.5
    assert float(demand.qty_remaining) == 1.5


def test_request_rejects_inactive_appraiser(db_session):
    ids = _ids(db_session)
    appraiser = db_session.get(User, ids["appraiser"])
    appraiser.is_active = False
    db_session.commit()

    with pytest.raises(RequestValidationError):
        create_request(
            db_session,
            ids["appraiser"],
            ids["branch"],
            None,
            [RequestLineInput(item_id=ids["packages"], qty_requested=1)],
        )

    assert db_session.query(DemandLine).count() == 0


def test_request_rejects_inactive_item(db_session):
    ids = _ids(db_session)
    item = db_session.get(Item, ids["packages"])
    item.is_active = False
    db_session.commit()

    with pytest.raises(RequestValidationError):
        create_request(
            db_session,
            ids["appraiser"],
            ids["branch"],
            None,
            [RequestLineInput(item_id=ids["packages"], qty_requested=1)],
        )

    assert db_session.query(DemandLine).count() == 0


def test_partial_delivery_and_next_request_are_merged(db_session):
    ids = _ids(db_session)
    create_request(
        db_session,
        ids["appraiser"],
        ids["branch"],
        None,
        [
            RequestLineInput(item_id=ids["packages"], qty_requested=20),
            RequestLineInput(item_id=ids["paper"], qty_requested=2),
        ],
    )
    session = get_or_open_delivery_session(db_session, ids["driver"], ids["branch"])
    package_demand = db_session.query(DemandLine).filter_by(item_id=ids["packages"]).one()
    paper_demand = db_session.query(DemandLine).filter_by(item_id=ids["paper"]).one()

    save_delivery_result(
        db_session,
        session.id,
        [
            DeliveryLineInput(demand_line_id=package_demand.id, qty_delivered_now=10),
            DeliveryLineInput(demand_line_id=paper_demand.id, qty_delivered_now=2),
        ],
    )
    create_request(
        db_session,
        ids["appraiser"],
        ids["branch"],
        None,
        [
            RequestLineInput(item_id=ids["packages"], qty_requested=5),
            RequestLineInput(item_id=ids["pens"], qty_requested=3),
        ],
    )

    package_demand = db_session.get(DemandLine, package_demand.id)
    paper_demand = db_session.get(DemandLine, paper_demand.id)
    pens_demand = db_session.query(DemandLine).filter_by(item_id=ids["pens"]).one()

    assert float(package_demand.qty_total_requested) == 25
    assert float(package_demand.qty_total_delivered) == 10
    assert float(package_demand.qty_remaining) == 15
    assert package_demand.status == DemandStatus.partially_delivered
    assert float(paper_demand.qty_remaining) == 0
    assert paper_demand.status == DemandStatus.delivered
    assert float(pens_demand.qty_remaining) == 3
    assert pens_demand.status == DemandStatus.active
    assert db_session.query(Request).count() == 1
    assert db_session.query(RequestLine).count() == 4


def test_fully_delivered_request_starts_new_request_history(db_session):
    ids = _ids(db_session)
    first_request = create_request(
        db_session,
        ids["appraiser"],
        ids["branch"],
        None,
        [RequestLineInput(item_id=ids["packages"], qty_requested=20)],
    )
    session = get_or_open_delivery_session(db_session, ids["driver"], ids["branch"])
    demand = db_session.query(DemandLine).one()
    save_delivery_result(
        db_session,
        session.id,
        [DeliveryLineInput(demand_line_id=demand.id, qty_delivered_now=20)],
    )

    second_request = create_request(
        db_session,
        ids["appraiser"],
        ids["branch"],
        None,
        [RequestLineInput(item_id=ids["pens"], qty_requested=3)],
    )

    assert first_request.id != second_request.id
    assert db_session.query(Request).count() == 2


def test_delivery_cannot_exceed_remaining(db_session):
    ids = _ids(db_session)
    create_request(
        db_session,
        ids["appraiser"],
        ids["branch"],
        None,
        [RequestLineInput(item_id=ids["packages"], qty_requested=20)],
    )
    session = get_or_open_delivery_session(db_session, ids["driver"], ids["branch"])
    demand = db_session.query(DemandLine).one()

    with pytest.raises(DeliveryValidationError):
        save_delivery_result(
            db_session,
            session.id,
            [DeliveryLineInput(demand_line_id=demand.id, qty_delivered_now=21)],
        )

    demand = db_session.get(DemandLine, demand.id)
    assert float(demand.qty_total_delivered) == 0
    assert float(demand.qty_remaining) == 20


def test_delivery_validation_does_not_partially_mutate_lines(db_session):
    ids = _ids(db_session)
    create_request(
        db_session,
        ids["appraiser"],
        ids["branch"],
        None,
        [
            RequestLineInput(item_id=ids["packages"], qty_requested=20),
            RequestLineInput(item_id=ids["paper"], qty_requested=2),
        ],
    )
    session = get_or_open_delivery_session(db_session, ids["driver"], ids["branch"])
    package_demand = db_session.query(DemandLine).filter_by(item_id=ids["packages"]).one()
    paper_demand = db_session.query(DemandLine).filter_by(item_id=ids["paper"]).one()

    with pytest.raises(DeliveryValidationError):
        save_delivery_result(
            db_session,
            session.id,
            [
                DeliveryLineInput(demand_line_id=package_demand.id, qty_delivered_now=5),
                DeliveryLineInput(demand_line_id=paper_demand.id, qty_delivered_now=3),
            ],
        )

    package_demand = db_session.get(DemandLine, package_demand.id)
    paper_demand = db_session.get(DemandLine, paper_demand.id)
    assert float(package_demand.qty_total_delivered) == 0
    assert float(package_demand.qty_remaining) == 20
    assert float(paper_demand.qty_total_delivered) == 0
    assert float(paper_demand.qty_remaining) == 2
    assert db_session.query(DeliverySessionLine).count() == 0


def test_delivery_requires_active_driver_and_branch(db_session):
    ids = _ids(db_session)
    driver = db_session.get(User, ids["driver"])
    branch = db_session.get(Branch, ids["branch"])

    driver.is_active = False
    db_session.commit()
    with pytest.raises(DeliveryValidationError):
        get_or_open_delivery_session(db_session, ids["driver"], ids["branch"])

    driver.is_active = True
    branch.is_active = False
    db_session.commit()
    with pytest.raises(DeliveryValidationError):
        get_or_open_delivery_session(db_session, ids["driver"], ids["branch"])

    assert db_session.query(DeliverySessionLine).count() == 0


def test_delivery_quantity_allows_decimal(db_session):
    ids = _ids(db_session)
    create_request(
        db_session,
        ids["appraiser"],
        ids["branch"],
        None,
        [RequestLineInput(item_id=ids["packages"], qty_requested=20)],
    )
    session = get_or_open_delivery_session(db_session, ids["driver"], ids["branch"])
    demand = db_session.query(DemandLine).one()

    save_delivery_result(
        db_session,
        session.id,
        [DeliveryLineInput(demand_line_id=demand.id, qty_delivered_now=1.5)],
    )

    demand = db_session.get(DemandLine, demand.id)
    assert float(demand.qty_total_delivered) == 1.5
    assert float(demand.qty_remaining) == 18.5


def test_delivery_saves_shortage_reason_only_for_not_full_lines(db_session):
    ids = _ids(db_session)
    create_request(
        db_session,
        ids["appraiser"],
        ids["branch"],
        None,
        [
            RequestLineInput(item_id=ids["packages"], qty_requested=20),
            RequestLineInput(item_id=ids["paper"], qty_requested=2),
        ],
    )
    session = get_or_open_delivery_session(db_session, ids["driver"], ids["branch"])
    package_demand = db_session.query(DemandLine).filter_by(item_id=ids["packages"]).one()
    paper_demand = db_session.query(DemandLine).filter_by(item_id=ids["paper"]).one()

    save_delivery_result(
        db_session,
        session.id,
        [
            DeliveryLineInput(
                demand_line_id=package_demand.id,
                qty_delivered_now=5,
                shortage_reason="Не было на складе",
            ),
            DeliveryLineInput(
                demand_line_id=paper_demand.id,
                qty_delivered_now=2,
                shortage_reason="Эта причина должна очиститься",
            ),
        ],
    )

    package_line = db_session.query(DeliverySessionLine).filter_by(item_id=ids["packages"]).one()
    paper_line = db_session.query(DeliverySessionLine).filter_by(item_id=ids["paper"]).one()
    assert package_line.shortage_reason == "Не было на складе"
    assert paper_line.shortage_reason is None


def test_admin_request_adjustment_updates_active_demand(db_session):
    ids = _ids(db_session)
    create_request(
        db_session,
        ids["appraiser"],
        ids["branch"],
        None,
        [RequestLineInput(item_id=ids["packages"], qty_requested=20)],
    )

    _adjust_active_demand(db_session, ids["branch"], ids["packages"], Decimal("-5"))
    db_session.commit()

    demand = db_session.query(DemandLine).one()
    assert float(demand.qty_total_requested) == 15
    assert float(demand.qty_remaining) == 15


def test_admin_request_delivery_guard_detects_saved_delivery(db_session):
    ids = _ids(db_session)
    request = create_request(
        db_session,
        ids["appraiser"],
        ids["branch"],
        None,
        [RequestLineInput(item_id=ids["packages"], qty_requested=20)],
    )
    assert not _request_has_delivery(db_session, request)
    session = get_or_open_delivery_session(db_session, ids["driver"], ids["branch"])
    demand = db_session.query(DemandLine).one()

    save_delivery_result(
        db_session,
        session.id,
        [DeliveryLineInput(demand_line_id=demand.id, qty_delivered_now=1)],
    )

    assert _request_has_delivery(db_session, request)


def test_same_demand_line_cannot_be_saved_twice_in_one_visit(db_session):
    ids = _ids(db_session)
    create_request(
        db_session,
        ids["appraiser"],
        ids["branch"],
        None,
        [RequestLineInput(item_id=ids["packages"], qty_requested=20)],
    )
    session = get_or_open_delivery_session(db_session, ids["driver"], ids["branch"])
    demand = db_session.query(DemandLine).one()

    save_delivery_result(
        db_session,
        session.id,
        [DeliveryLineInput(demand_line_id=demand.id, qty_delivered_now=5)],
    )

    with pytest.raises(DeliveryValidationError):
        save_delivery_result(
            db_session,
            session.id,
            [DeliveryLineInput(demand_line_id=demand.id, qty_delivered_now=5)],
        )

    demand = db_session.get(DemandLine, demand.id)
    assert float(demand.qty_total_delivered) == 5
    assert float(demand.qty_remaining) == 15
    assert db_session.query(DeliverySessionLine).count() == 1


def test_closed_session_cannot_be_edited(db_session):
    ids = _ids(db_session)
    create_request(
        db_session,
        ids["appraiser"],
        ids["branch"],
        None,
        [RequestLineInput(item_id=ids["packages"], qty_requested=20)],
    )
    session = get_or_open_delivery_session(db_session, ids["driver"], ids["branch"])
    demand = db_session.query(DemandLine).one()
    close_delivery_session(db_session, session.id)

    with pytest.raises(DeliveryValidationError):
        save_delivery_result(
            db_session,
            session.id,
            [DeliveryLineInput(demand_line_id=demand.id, qty_delivered_now=1)],
        )

    assert db_session.query(Request).count() == 1
