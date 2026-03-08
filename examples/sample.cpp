// 示例 C++ 代碼：展示各種程式結構
// 用於測試 OmniTrace 的解析和分析功能

#include <iostream>
#include <vector>
#include <string>
#include "sample.h"

// 全局變數
int globalCounter = 0;
const std::string APP_NAME = "OmniTrace";

// 類別定義：基礎類別
class Shape {
protected:
    double area;
    std::string name;

public:
    Shape(const std::string& n) : name(n), area(0.0) {}
    
    virtual ~Shape() {}
    
    virtual double calculateArea() = 0;
    
    std::string getName() const {
        return name;
    }
};

// 類別繼承：展示繼承關係
class Circle : public Shape {
private:
    double radius;

public:
    Circle(double r) : Shape("Circle"), radius(r) {
        area = calculateArea();
    }
    
    double calculateArea() override {
        return 3.14159 * radius * radius;
    }
    
    void setRadius(double r) {
        radius = r;
        area = calculateArea();
    }
};

class Rectangle : public Shape {
private:
    double width;
    double height;

public:
    Rectangle(double w, double h) 
        : Shape("Rectangle"), width(w), height(h) {
        area = calculateArea();
    }
    
    double calculateArea() override {
        return width * height;
    }
};

// God Object 示例：過度耦合的管理類
class ShapeManager {
private:
    std::vector<Shape*> shapes;
    int totalShapes;
    double totalArea;

public:
    ShapeManager() : totalShapes(0), totalArea(0.0) {}
    
    ~ShapeManager() {
        for (auto shape : shapes) {
            delete shape;
        }
    }
    
    void addShape(Shape* shape) {
        shapes.push_back(shape);
        totalShapes++;
        totalArea += shape->calculateArea();
    }
    
    void removeShape(int index) {
        if (index >= 0 && index < shapes.size()) {
            totalArea -= shapes[index]->calculateArea();
            delete shapes[index];
            shapes.erase(shapes.begin() + index);
            totalShapes--;
        }
    }
    
    double getTotalArea() const {
        return totalArea;
    }
    
    int getCount() const {
        return totalShapes;
    }
    
    void displayAll() {
        for (const auto& shape : shapes) {
            std::cout << shape->getName() 
                      << ": " << shape->calculateArea() << std::endl;
        }
    }
};

// 高複雜度函數示例
int processData(int* data, int size, int threshold) {
    int result = 0;
    
    for (int i = 0; i < size; i++) {
        if (data[i] > threshold) {
            if (data[i] % 2 == 0) {
                result += data[i] * 2;
            } else {
                result += data[i];
            }
        } else if (data[i] < 0) {
            if (data[i] % 3 == 0) {
                result -= data[i];
            }
        } else {
            result += threshold;
        }
        
        // 嵌套條件
        if (result > 1000) {
            if (i < size / 2) {
                result /= 2;
            } else {
                result *= 0.9;
            }
        }
    }
    
    return result;
}

// 函數調用鏈示例
void helperFunction() {
    globalCounter++;
    std::cout << "Helper called, counter: " << globalCounter << std::endl;
}

void middleFunction(int value) {
    if (value > 0) {
        helperFunction();
    } else {
        std::cout << "Negative value" << std::endl;
    }
}

void topLevelFunction(int data) {
    for (int i = 0; i < data; i++) {
        middleFunction(i - 5);
    }
}

// 可能導致循環依賴的設計
class ModuleA;  // 前向聲明

class ModuleB {
private:
    ModuleA* moduleA;

public:
    void setModuleA(ModuleA* a) {
        moduleA = a;
    }
    
    void processB();
};

class ModuleA {
private:
    ModuleB* moduleB;

public:
    ModuleA() {
        moduleB = new ModuleB();
        moduleB->setModuleA(this);
    }
    
    ~ModuleA() {
        delete moduleB;
    }
    
    void processA() {
        moduleB->processB();
    }
};

void ModuleB::processB() {
    std::cout << "Processing in ModuleB" << std::endl;
}

// 主函數
int main() {
    // 創建形狀
    Circle circle(5.0);
    Rectangle rect(4.0, 6.0);
    
    // 使用 ShapeManager
    ShapeManager manager;
    manager.addShape(new Circle(3.0));
    manager.addShape(new Rectangle(2.0, 8.0));
    
    std::cout << "Total area: " << manager.getTotalArea() << std::endl;
    manager.displayAll();
    
    // 測試高複雜度函數
    int testData[] = {1, -5, 10, 15, -9, 20, 25};
    int result = processData(testData, 7, 10);
    std::cout << "Processed result: " << result << std::endl;
    
    // 測試函數調用鏈
    topLevelFunction(10);
    
    // 測試循環依賴
    ModuleA moduleA;
    moduleA.processA();
    
    return 0;
}
