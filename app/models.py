from . import db
from flask.ext.login import UserMixin,AnonymousUserMixin
from . import login_manager
from datetime import datetime
from markdown import markdown
import bleach
from jieba.analyse.analyzer import ChineseAnalyzer

# 装饰器not_student_login 所需要的模块
from functools import wraps
from flask import _request_ctx_stack, abort, current_app, flash, redirect, request, session, url_for, \
    has_request_context
from flask.ext.login import current_user


# 此装饰器用于学生没有权限访问的页面
def not_student_login(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if current_app.login_manager._login_disabled:
            return func(*args, **kwargs)
        elif not current_user.is_authenticated:
            return current_app.login_manager.unauthorized()
        elif current_user.roleId == 0:
            return redirect('/')
        return func(*args, **kwargs)

    return decorated_view


# 装饰器: 更新 InternshipInfor 实习状态
def update_intern_internStatus(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        now = datetime.now().date()
        db.session.execute('update InternshipInfor set internStatus=0 where start > "%s"' % now)
        db.session.execute('update InternshipInfor set internStatus=1 where start < "%s" and end > "%s"' % (now, now))
        db.session.execute('update InternshipInfor set internStatus=2 where end < "%s"' % now)
        return func(*args, **kwargs)

    return decorated_view


# 装饰器: 更新 InternshipInfor 日志审核状态
# uncheck intern.jourcheck when there is uncheck valid jour
def update_intern_jourCheck(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        db.session.execute(' \
            UPDATE InternshipInfor AS a, \
                   (SELECT DISTINCT internId \
                      FROM Journal \
                     WHERE isvalid = 1 \
                       AND jourCheck = 0) AS b \
               SET a.jourCheck = 0 \
             WHERE a.jourCheck = 1 \
               AND a.Id = b.internId')
        return func(*args, **kwargs)
    return decorated_view


#装饰器：更新grade，major，classes表
def update_grade_major_classes(func):
    @wraps(func)
    def decorator(*args,**kwargs):
        grades=db.session.execute('Select distinct grade from Student')
        majors=db.session.execute('Select distinct major from Student')
        classess=db.session.execute('Select distinct classes from Student')
        try:
            for grade in grades:
                if Grade.query.filter_by(grade=grade.grade).count()==0:
                    g=Grade(grade=grade.grade)
                    db.session.add(g)
            for classes in classess:
                if Classes.query.filter_by(classes=classes.classes).count()==0:
                    c=Classes(classes=classes.classes)
                    db.session.add(c)
            for major in majors:
                if Major.query.filter_by(major=major.major).count()==0:
                    m=Major(major=major.major)
                    db.session.add(m)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print('更新年级，班级，专业：',e)
        return func(*args, **kwargs)
    return decorator


@login_manager.user_loader
def load_user(Id):
    '''维持session，由于http为无状态，每次请求都要从上一个session中获取已登陆的用户'''
    return Teacher.query.get(Id) or Student.query.get(Id)


class Role(db.Model):
    __tablename__ = 'Role'
    roleId = db.Column(db.Integer, primary_key=True)
    roleName = db.Column(db.String(5), unique=True)
    permission = db.Column(db.String(8), unique=True)
    # backref='role'可代替Teacher的roleId
    roleDescribe = db.Column(db.String(200))
    teacher = db.relationship('Teacher', backref='role', lazy='dynamic')
    student = db.relationship('Student', backref='role', lazy='dynamic')

    def __repr__(self):
        return '<Role %r>' % self.name

    # 对角色进行权限判断
    @staticmethod
    def can(role, permissions):
        if role.permission is not None:
            p = eval(role.permission)
        return (p & permissions) == permissions


class Teacher(db.Model, UserMixin):
    __tablename__ = 'Teacher'
    teaId = db.Column(db.String(10), primary_key=True)
    teaName = db.Column(db.String(4), index=True)
    teaSex = db.Column(db.String(2))
    roleId = db.Column(db.Integer, db.ForeignKey('Role.roleId'), default=1)
    password = db.Column(db.String(10))
    teaPosition = db.Column(db.String(20))
    teaPhone = db.Column(db.String(15))
    teaEmail = db.Column(db.String(20))

    def get_id(self):
        return self.teaId

    # 对教师用户进行权限判断
    def can(self, permissions):
        if self.role.permission is not None:
            p = eval(self.role.permission)
        return (p & permissions) == permissions

    def __repr__(self):
        return '<Teacher %r>' % self.teaName

    # 创建大量虚拟信息
    @staticmethod
    def generate_fake(count=100):
        from sqlalchemy.exc import IntegrityError
        from random import seed, randint, choice
        import forgery_py

        seed()
        for i in range(count):
            teacher = Teacher(
                teaId=randint(20000000, 20160000),
                teaName=forgery_py.internet.user_name(True),
                teaSex=choice(['男', '女']),
                password='123')
            db.session.add(teacher)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()


class Student(db.Model, UserMixin):
    __tablename__ = 'Student'
    stuId = db.Column(db.String(20), primary_key=True)
    stuName = db.Column(db.String(10), index=True)
    institutes = db.Column(db.String(10))
    major = db.Column(db.String(10))
    grade = db.Column(db.String(10))
    sex = db.Column(db.String(2))
    classes = db.Column(db.String(10))
    internCheck = db.Column(db.Integer, default=0)
    jourCheck = db.Column(db.Integer, default=0)
    sumCheck = db.Column(db.Integer, default=0)
    roleId = db.Column(db.Integer, db.ForeignKey('Role.roleId'), default=0)
    password = db.Column(db.String(10))
    internshipinfor = db.relationship('InternshipInfor', backref='student', lazy='dynamic')



    def get_id(self):
        return self.stuId

    # 对学生用户进行权限判断
    def can(self, permissions):
        if self.role.permission is not None:
            p = eval(self.role.permission)
        return (p & permissions) == permissions

    def __repr__(self):
        return '<Student %r>' % self.stuName

    # 创建大量虚拟信息
    @staticmethod
    def generate_fake(count=100):
        from sqlalchemy.exc import IntegrityError
        from random import seed, randint, choice
        import forgery_py

        seed()
        for i in range(count):
            student = Student(
                stuId=randint(201300000000, 201600000000),
                stuName=forgery_py.internet.user_name(True),
                institutes='计算机与网络安全学院',
                # institutes='计算机学院',
                major=choice(['计算机科学与技术', '网络工程', '软件工程', '信息科学与技术']),
                grade=choice([2013, 2014, 2015, 2016]),
                classes=randint(1, 10),
                sex=choice(['男', '女']),
                password='123'
            )
            db.session.add(student)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()


class ComInfor(db.Model):
    __tablename__ = 'ComInfor'
    __searchable__ = ['comName']
    __analyzer__=ChineseAnalyzer()

    comId = db.Column(db.Integer, primary_key=True)
    comName = db.Column(db.String(50))
    comBrief = db.Column(db.String(500))
    comCity=db.Column(db.String(20))
    comAddress = db.Column(db.String(100))
    comUrl = db.Column(db.String(100),default="暂无")
    comMon = db.Column(db.String(20))
    comProject = db.Column(db.String(250))
    comStaff = db.Column(db.String(20))
    comContact = db.Column(db.String(20))
    comPhone = db.Column(db.String(20))
    comEmail = db.Column(db.String(50))
    comFax = db.Column(db.String(20))
    comDate = db.Column(db.DATETIME, default=datetime.now)
    students = db.Column(db.Integer, default=0)
    comCheck = db.Column(db.Integer, default=0)
    internshipinfor = db.relationship('InternshipInfor', backref='cominfor', lazy='dynamic')

    # 创建大量虚拟信息
    @staticmethod
    def generate_fake(count=100):
        from sqlalchemy.exc import IntegrityError
        from random import seed, randint, choice
        import forgery_py

        seed()
        for i in range(count):
            comInfor = ComInfor(comName=forgery_py.internet.user_name(True),
                                comBrief=forgery_py.lorem_ipsum.sentences(),
                                comAddress=forgery_py.address.city(), comUrl=forgery_py.internet.domain_name(),
                                comMon=randint(100, 10000), comProject=forgery_py.lorem_ipsum.word(),
                                comStaff=randint(100, 10000),
                                comContact=forgery_py.name.full_name(), comPhone=forgery_py.address.phone(),
                                comEmail=forgery_py.internet.email_address(user=None),
                                comFax=forgery_py.address.phone())
            db.session.add(comInfor)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()

    def __str__(self):
        return self.comName


#由于校内指导老师与学生实习信息是多对多关系，把SchDirTea设置为第三张对应表
#对于InternshipInfor类和Teacher类可以直接 实例名.schdirtea和实例名.students
SchDirTea=db.Table('SchDirTea',
    db.Column('teaId',db.String(20),db.ForeignKey('Teacher.teaId')),
    db.Column('internId',db.Integer,db.ForeignKey('InternshipInfor.Id')))

class InternshipInfor(db.Model):
    __tablename__ = 'InternshipInfor'
    Id = db.Column(db.Integer, primary_key=True)
    task = db.Column(db.String(500))
    # 岗位信息
    post = db.Column(db.String(100))
    opinion = db.Column(db.String(250))
    start = db.Column(db.Date)
    end = db.Column(db.Date)
    internStatus = db.Column(db.Integer, index=True)
    time = db.Column(db.DATETIME, default=datetime.now())
    icheckTeaId = db.Column(db.String(8))
    internCheck = db.Column(db.Integer, default=0)
    internStatus = db.Column(db.Integer, default=0)
    icheckTime = db.Column(db.DATETIME)
    #cominfor
    comId = db.Column(db.Integer, db.ForeignKey('ComInfor.comId'))
    #student
    stuId = db.Column(db.String(20), db.ForeignKey('Student.stuId'))
    jourCheck = db.Column(db.Integer, default=0)
    #InternshipInfor.schdirtea  #Teacher.internshipinfor
    schdirtea=db.relationship('Teacher',secondary=SchDirTea,backref=db.backref('internshipinfor',lazy='dynamic'),lazy='dynamic')


class ComDirTea(db.Model):
    __tablename__ = 'ComDirTea'
    Id = db.Column(db.Integer, primary_key=True)
    cteaName = db.Column(db.String(10))
    cteaDuty = db.Column(db.String(20))
    cteaPhone = db.Column(db.String(15))
    cteaEmail = db.Column(db.String(20))
    comId = db.Column(db.Integer, db.ForeignKey('ComInfor.comId'))
    stuId = db.Column(db.String(20), db.ForeignKey('Student.stuId'))
    internId=db.Column(db.Integer)

class Summary(db.Model):
    __tablename__ = 'Summary'
    internId = db.Column(db.Integer, primary_key=True)
    sumCheck = db.Column(db.Integer)
    sumCheckTeaId = db.Column(db.String(10))
    sumCheckTime = db.Column(db.DATETIME)
    sumCheckOpinion = db.Column(db.String(250))
    comScore = db.Column(db.Integer,default=0)
    schScore = db.Column(db.Integer,default=0)
    sumScore = db.Column(db.Integer,default=0)
    uploaded=db.Column(db.Integer,default=0)


class Journal(db.Model):
    __tablename__ = 'Journal'
    Id = db.Column(db.Integer, primary_key=True)
    stuId = db.Column(db.String(20), db.ForeignKey('Student.stuId'))
    comId = db.Column(db.Integer, db.ForeignKey('ComInfor.comId'))
    weekNo = db.Column(db.Integer, default=1)
    workStart = db.Column(db.DATE)
    workEnd = db.Column(db.DATE)
    mon = db.Column(db.String(1000), default=' ')
    tue = db.Column(db.String(1000), default=' ')
    wed = db.Column(db.String(1000), default=' ')
    thu = db.Column(db.String(1000), default=' ')
    fri = db.Column(db.String(1000), default=' ')
    sat = db.Column(db.String(1000), default=' ')
    sun = db.Column(db.String(1000), default=' ')
    jcheckTeaId = db.Column(db.String(8))
    jourCheck = db.Column(db.Integer, default=0)
    jcheckTime = db.Column(db.DATETIME)
    internId = db.Column(db.Integer, db.ForeignKey('InternshipInfor.Id'))
    opinion = db.Column(db.String(500), default='')
    isoweek = db.Column(db.Integer)
    isoyear = db.Column(db.Integer)
    isvalid = db.Column(db.Integer)

class Grade(db.Model):
    __tablename__='Grade'
    grade=db.Column(db.Integer,primary_key=True)

class Major(db.Model):
    __tablename__='Major'
    major=db.Column(db.String(20),primary_key=True)

class Classes(db.Model):
    __tablename__='Classes'
    classes=db.Column(db.Integer,primary_key=True)

class Visit(db.Model):
    __tablename__='Visit'
    visitId=db.Column(db.Integer,primary_key=True)
    userId=db.Column(db.String(13))
    filename=db.Column(db.String(50))
    time=db.Column(db.DATETIME)
    vteaName=db.Column(db.String(10))
    visitTime=db.Column(db.DATETIME)
    visitWay=db.Column(db.String(2))
    

class Visit_Intern(db.Model):
    __tablename__='Visit_Intern'
    visitId=db.Column(db.Integer,primary_key=True)
    internId=db.Column(db.Integer,primary_key=True)

class Permission:
    # 企业信息查询
    COM_INFOR_SEARCH = 0X0000009
    # 企业信息编辑
    COM_INFOR_EDIT = 0X000000B
    # 企业信息审核
    COM_INFOR_CHECK = 0X000000F

    # 实习企业信息列表
    INTERNCOMPANY_LIST = 0X0000008
    # 学生实习信息列表
    STU_INTERN_LIST = 0X0000010

    # 学生实习信息查看
    STU_INTERN_SEARCH = 0X0000030
    # 学生实习信息编辑
    STU_INTERN_EDIT = 0X0000070
    # 学生实习信息审核
    STU_INTERN_CHECK = 0X00000F0

    # 学生实习日志查询
    STU_JOUR_SEARCH = 0X0000210
    # 学生实习日志编辑
    STU_JOUR_EDIT = 0X0000610
    # 学生实习日志审核
    STU_JOUR_CHECK = 0X0000E10

    # 学生实习总结查看
    STU_SUM_SEARCH = 0X0001010
    # 学生实习总结编辑
    STU_SUM_EDIT = 0X0003010
    # 学生实习总结和成果审核
    STU_SUM_SCO_CHECK = 0X0007010

    # 学生信息管理
    STU_INTERN_MANAGE = 0X0010000
    # 老师信息管理
    TEA_INFOR_MANAGE = 0X0020000
    # 权限管理
    PERMIS_MANAGE = 0X0040000
    #下拉框管理
    SELECT_MANAGE=0X0080000
    #上传探访记录
    UPLOAD_VISIT= 0X0100030
    #修改首页介绍
    ALTER_INTRODUCE=0X0200000

class AnonymousUser(AnonymousUserMixin):
    def can(self,permissions):
        return False

login_manager.anonymous_user=AnonymousUser

class Introduce(db.Model):
    __tablename__='Introduce'
    Id=db.Column(db.Integer,primary_key=True)
    content=db.Column(db.String(2000))
    time=db.Column(db.DATE)
    content_html=db.Column(db.String(2000))

    @staticmethod
    def change_content(target,value,oldvalue,initiator):
        allowed_tags=['a','abbr','acronym','b','blockquote','code','em','i','li','ol','pre','strong','ul','h1','h2','h3','p']
        target.content_html=bleach.linkify(bleach.clean(markdown(value,output_format='html'),tags=allowed_tags,strip=True))
db.event.listen(Introduce.content,'set',Introduce.change_content)
        

